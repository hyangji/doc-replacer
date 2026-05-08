"""Excel file parsing service for batch replacement mappings.

Parses Excel files (.xlsx) containing replacement data and maps
them to HWPX table structures for targeted modifications.
"""

from io import BytesIO

import openpyxl

from app.services.hwp_service import HwpService


class ExcelServiceError(Exception):
    """Base exception for Excel service errors."""


class ExcelParseError(ExcelServiceError):
    """Raised when Excel file parsing fails."""


# Known header variations (Korean and English)
FIELD_NAME_HEADERS = {"필드명", "필드", "field_name", "field", "항목", "항목명"}
OLD_VALUE_HEADERS = {"원본", "원본값", "old_value", "old", "기존", "기존값", "찾을내용", "찾기"}
NEW_VALUE_HEADERS = {"수정", "수정값", "new_value", "new", "변경", "변경값", "바꿀내용", "바꾸기"}


class ExcelService:
    """Service for Excel-based batch replacement operations."""

    def __init__(self) -> None:
        self._hwp_service = HwpService()

    async def parse_excel(self, file_content: bytes) -> dict:
        """Parse an Excel file and extract sheet-level data.

        Returns: {
            "sheets": [{
                "name": str,
                "headers": list[str],
                "rows": list[list[str]],
            }]
        }
        """
        try:
            wb = openpyxl.load_workbook(
                BytesIO(file_content), read_only=True, data_only=True
            )
        except Exception as e:
            raise ExcelParseError(f"엑셀 파일을 열 수 없습니다: {e}")

        sheets = []
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                sheets.append({"name": ws.title, "headers": [], "rows": []})
                continue

            headers = [str(c) if c is not None else "" for c in rows[0]]
            data_rows = [
                [str(c) if c is not None else "" for c in row]
                for row in rows[1:]
                if row and any(c is not None for c in row)
            ]
            sheets.append({
                "name": ws.title,
                "headers": headers,
                "rows": data_rows,
            })

        wb.close()

        if not sheets:
            raise ExcelParseError("엑셀 파일에 시트가 없습니다.")

        return {"sheets": sheets}

    async def create_mapping(
        self, excel_data: dict, hwpx_tables: list[dict]
    ) -> list[dict]:
        """Create mapping rules between Excel data and HWPX table cells.

        Maps Excel rows to HWPX table cells by matching header names
        and first-column values.

        Args:
            excel_data: Output from parse_excel().
            hwpx_tables: Output from HwpService.extract_tables().

        Returns:
            List of {
                "table_index": int,
                "row": int,
                "col": int,
                "old_value": str,
                "new_value": str,
                "field_name": str,
            }
        """
        mappings: list[dict] = []

        # Extract replacement pairs from the first sheet
        replacements = self._extract_replacements_from_sheets(excel_data)

        for r in replacements:
            old_val = r["old_value"]
            for table in hwpx_tables:
                for row_idx, row in enumerate(table.get("rows", [])):
                    for col_idx, cell_text in enumerate(row):
                        if old_val and old_val in cell_text:
                            mappings.append({
                                "table_index": table["index"],
                                "row": row_idx,
                                "col": col_idx,
                                "old_value": old_val,
                                "new_value": r["new_value"],
                                "field_name": r.get("field_name", ""),
                            })

        return mappings

    async def apply_replacements(
        self, file_data: bytes, mappings: list[dict]
    ) -> tuple[bytes, list[dict]]:
        """Apply replacement mappings to HWPX file data (in-memory).

        Args:
            file_data: HWPX file bytes.
            mappings: List of mapping dicts (from create_mapping or parse_replacement_excel).

        Returns:
            (modified_file_data, change_log)
            change_log: [{"field_name": str, "old_value": str, "new_value": str, "count": int}]
        """
        current_data = file_data
        change_log: list[dict] = []

        for m in mappings:
            old_val = m.get("old_value", "")
            new_val = m.get("new_value", "")
            if not old_val:
                continue

            new_data, count = self._hwp_service.replace_text(
                current_data, old_val, new_val
            )
            change_log.append({
                "field_name": m.get("field_name", ""),
                "old_value": old_val,
                "new_value": new_val,
                "count": count,
            })
            if count > 0:
                current_data = new_data

        return current_data, change_log

    async def preview_mappings(
        self, excel_data: dict, hwpx_tables: list[dict]
    ) -> list[dict]:
        """Generate preview of what will be replaced (without modifying files).

        Returns:
            List of {
                "field_name": str,
                "old_value": str,
                "new_value": str,
                "match_count": int,
                "matched_locations": [{"table_index": int, "row": int, "col": int}],
            }
        """
        replacements = self._extract_replacements_from_sheets(excel_data)
        preview: list[dict] = []

        for r in replacements:
            old_val = r["old_value"]
            locations: list[dict] = []

            for table in hwpx_tables:
                for row_idx, row in enumerate(table.get("rows", [])):
                    for col_idx, cell_text in enumerate(row):
                        if old_val and old_val in cell_text:
                            locations.append({
                                "table_index": table["index"],
                                "row": row_idx,
                                "col": col_idx,
                            })

            preview.append({
                "field_name": r.get("field_name", ""),
                "old_value": old_val,
                "new_value": r["new_value"],
                "match_count": len(locations),
                "matched_locations": locations,
            })

        return preview

    def _extract_replacements_from_sheets(self, excel_data: dict) -> list[dict]:
        """Extract replacement pairs from parsed Excel data."""
        sheets = excel_data.get("sheets", [])
        if not sheets:
            return []

        # Use first sheet
        sheet = sheets[0]
        headers = sheet.get("headers", [])
        rows = sheet.get("rows", [])

        col_map = _detect_columns_from_list(headers)

        if col_map is None:
            # Fallback: assume A=field_name, B=old_value, C=new_value
            if len(headers) >= 3:
                col_map = {"field_name": 0, "old_value": 1, "new_value": 2}
            elif len(headers) >= 2:
                col_map = {"old_value": 0, "new_value": 1}
            else:
                return []

        replacements: list[dict] = []
        for row_idx, row in enumerate(rows):
            old_val = _safe_get(row, col_map.get("old_value"))
            new_val = _safe_get(row, col_map.get("new_value"))
            if not old_val:
                continue

            field_name = _safe_get(row, col_map.get("field_name"))
            if not field_name:
                field_name = f"row_{row_idx + 2}"

            replacements.append({
                "field_name": field_name,
                "old_value": old_val,
                "new_value": new_val,
            })

        return replacements


# ── Module-level functions (backward compatibility) ──


def parse_replacement_excel(file_content: bytes) -> list[dict]:
    """Parse an Excel file and extract replacement mappings.

    Returns: List of {"field_name": str, "old_value": str, "new_value": str}
    """
    try:
        wb = openpyxl.load_workbook(
            BytesIO(file_content), read_only=True, data_only=True
        )
    except Exception as e:
        raise ExcelParseError(f"엑셀 파일을 열 수 없습니다: {e}")

    ws = wb.active
    if ws is None:
        raise ExcelParseError("엑셀 파일에 시트가 없습니다.")

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise ExcelParseError("엑셀 파일이 비어 있습니다.")

    col_map = _detect_columns(rows[0])
    data_rows = rows[1:]

    if col_map is None:
        if len(rows[0]) < 2:
            raise ExcelParseError(
                "엑셀 파일에 최소 2개 이상의 열이 필요합니다 (원본, 수정)."
            )
        col_map = _default_col_map(len(rows[0]))
        data_rows = rows

    replacements = []
    for row_idx, row in enumerate(data_rows, start=2):
        if not row or all(cell is None for cell in row):
            continue

        old_val = _cell_str(row, col_map["old_value"])
        new_val = _cell_str(row, col_map["new_value"])

        if not old_val:
            continue

        field_name = _cell_str(row, col_map.get("field_name"))
        if not field_name:
            field_name = f"row_{row_idx}"

        replacements.append({
            "field_name": field_name,
            "old_value": old_val,
            "new_value": new_val,
        })

    if not replacements:
        raise ExcelParseError("엑셀 파일에서 유효한 교체 항목을 찾을 수 없습니다.")

    return replacements


def parse_excel_preview(file_content: bytes) -> dict:
    """Parse Excel file and return preview data."""
    try:
        wb = openpyxl.load_workbook(
            BytesIO(file_content), read_only=True, data_only=True
        )
    except Exception as e:
        raise ExcelParseError(f"엑셀 파일을 열 수 없습니다: {e}")

    ws = wb.active
    if ws is None:
        raise ExcelParseError("엑셀 파일에 시트가 없습니다.")

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise ExcelParseError("엑셀 파일이 비어 있습니다.")

    headers = [str(c) if c is not None else "" for c in rows[0]]
    data_rows = [
        [str(c) if c is not None else "" for c in row]
        for row in rows[1:]
        if row and any(c is not None for c in row)
    ]

    replacements = parse_replacement_excel(file_content)

    return {
        "headers": headers,
        "rows": data_rows,
        "total_rows": len(data_rows),
        "replacements": replacements,
    }


def map_excel_to_tables(
    replacements: list[dict],
    tables: list[dict],
) -> list[dict]:
    """Map Excel replacement data to HWPX table cells for targeted replacement.

    Args:
        replacements: list of {"field_name": str, "old_value": str, "new_value": str}
        tables: list of {"index": int, "rows": list[list[str]], "headers": list[str]}

    Returns:
        List of replacement dicts with matched_tables locations.
    """
    mapped = []
    for r in replacements:
        old_val = r["old_value"]
        matches = []
        for table in tables:
            for row_idx, row in enumerate(table.get("rows", [])):
                for col_idx, cell_text in enumerate(row):
                    if old_val and old_val in cell_text:
                        matches.append({
                            "table_index": table["index"],
                            "row": row_idx,
                            "col": col_idx,
                        })
        mapped.append({
            **r,
            "matched_tables": matches,
        })
    return mapped


def build_replacement_diff(
    replacements: list[dict],
    old_text: str,
    new_text: str,
) -> list[dict]:
    """Build a diff record for each replacement showing before/after."""
    diff_records = []
    for r in replacements:
        count = old_text.count(r["old_value"])
        diff_records.append({
            "field_name": r["field_name"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "found_count": count,
            "applied": count > 0,
        })
    return diff_records


# ── Internal helpers ──


def _detect_columns(header_row: tuple) -> dict | None:
    if not header_row:
        return None
    headers_lower = [str(h).strip().lower() if h else "" for h in header_row]
    return _match_headers(headers_lower)


def _detect_columns_from_list(headers: list[str]) -> dict | None:
    if not headers:
        return None
    headers_lower = [h.strip().lower() for h in headers]
    return _match_headers(headers_lower)


def _match_headers(headers_lower: list[str]) -> dict | None:
    col_map: dict = {}
    for idx, h in enumerate(headers_lower):
        if h in FIELD_NAME_HEADERS:
            col_map["field_name"] = idx
        elif h in OLD_VALUE_HEADERS:
            col_map["old_value"] = idx
        elif h in NEW_VALUE_HEADERS:
            col_map["new_value"] = idx

    if "old_value" not in col_map or "new_value" not in col_map:
        return None
    return col_map


def _default_col_map(num_cols: int) -> dict:
    if num_cols >= 3:
        return {"field_name": 0, "old_value": 1, "new_value": 2}
    return {"old_value": 0, "new_value": 1}


def _cell_str(row: tuple, col_idx: int | None) -> str:
    if col_idx is None or col_idx >= len(row):
        return ""
    val = row[col_idx]
    return str(val).strip() if val is not None else ""


def _safe_get(row: list, col_idx: int | None) -> str:
    if col_idx is None or col_idx >= len(row):
        return ""
    val = row[col_idx]
    return str(val).strip() if val else ""
