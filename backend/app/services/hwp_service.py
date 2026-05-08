"""HWP/HWPX file processing service.

Provides a unified HwpService class for both HWP (binary) and HWPX (ZIP+XML) formats.
All file operations work with in-memory bytes (no local file system dependency).
"""

import io
import os
import re
import zipfile
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as SafeET

HWPX_NAMESPACES = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
}

for prefix, uri in HWPX_NAMESPACES.items():
    ET.register_namespace(prefix, uri)

ALLOWED_EXTENSIONS = {".hwp", ".hwpx"}


class HwpServiceError(Exception):
    """Base exception for HWP service errors."""


class HwpConversionError(HwpServiceError):
    """Raised when HWP binary conversion is not available."""


class HwpParseError(HwpServiceError):
    """Raised when file parsing fails."""


def detect_file_type(filename: str) -> str:
    """Detect HWP or HWPX from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".hwpx":
        return "hwpx"
    elif ext == ".hwp":
        return "hwp"
    raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


def _get_local_name(tag: str) -> str:
    """Extract local name from a possibly namespaced XML tag."""
    return tag.split("}")[-1] if "}" in tag else tag


class HwpService:
    """Unified service for HWP/HWPX file processing (in-memory)."""

    # ── HWPX XML helpers ──

    @staticmethod
    def _get_section_files(zf: zipfile.ZipFile) -> list[str]:
        """Find all section XML files inside the HWPX archive."""
        section_files = []
        for name in zf.namelist():
            lower = name.lower()
            if ("contents/section" in lower or "contents/content" in lower) and lower.endswith(".xml"):
                section_files.append(name)
        section_files.sort()
        return section_files

    @staticmethod
    def _extract_text_elements(root: ET.Element) -> list[ET.Element]:
        """Find all <t> text elements in an XML tree."""
        return [
            el for el in root.iter()
            if _get_local_name(el.tag) == "t" and el.text
        ]

    # ── Core API (bytes-based) ──

    async def parse_file(self, file_data: bytes) -> dict:
        """Parse an HWPX file and extract text, tables, and metadata.

        Returns: {"text": str, "tables": list[dict], "metadata": dict}
        """
        self._validate_zip_data(file_data)
        text = self._extract_text_from_bytes(file_data)
        tables = self._extract_tables_from_bytes(file_data)
        metadata = self._extract_metadata_from_bytes(file_data)
        return {"text": text, "tables": tables, "metadata": metadata}

    async def extract_tables(self, file_data: bytes) -> list[dict]:
        """Extract all tables from an HWPX file.

        Each table: {"index": int, "rows": list[list[str]], "headers": list[str]}
        """
        self._validate_zip_data(file_data)
        return self._extract_tables_from_bytes(file_data)

    async def get_text_content(self, file_data: bytes) -> str:
        """Extract full text content for editor display."""
        self._validate_zip_data(file_data)
        return self._extract_text_from_bytes(file_data)

    async def save_file(self, file_data: bytes, content: str) -> bytes:
        """Save modified text content back into HWPX bytes. Returns new bytes."""
        self._validate_zip_data(file_data)
        new_lines = content.split("\n")
        line_idx = 0

        buf_in = io.BytesIO(file_data)
        buf_out = io.BytesIO()

        with zipfile.ZipFile(buf_in, "r") as zf_in:
            section_files = set(self._get_section_files(zf_in))
            with zipfile.ZipFile(buf_out, "w", zipfile.ZIP_DEFLATED) as zf_out:
                for item in zf_in.infolist():
                    data = zf_in.read(item.filename)
                    if item.filename in section_files:
                        root = SafeET.fromstring(data)
                        t_elements = self._extract_text_elements(root)
                        for t_el in t_elements:
                            if line_idx < len(new_lines):
                                t_el.text = new_lines[line_idx]
                                line_idx += 1
                            else:
                                t_el.text = ""
                        data = ET.tostring(
                            root, encoding="unicode", xml_declaration=True
                        ).encode("utf-8")
                    zf_out.writestr(item, data)

        return buf_out.getvalue()

    # ── Search / Replace (bytes-based) ──

    def search_text(
        self,
        file_data: bytes,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> list[dict]:
        """Search for text occurrences in file data."""
        from app.services.search_service import _validate_regex

        full_text = self._extract_text_from_bytes(file_data)
        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            _validate_regex(query)
        try:
            pattern = re.compile(query if use_regex else re.escape(query), flags)
        except re.error as e:
            raise HwpServiceError(f"잘못된 정규식 패턴입니다: {e}")

        matches = []
        for m in pattern.finditer(full_text):
            start = max(0, m.start() - 30)
            end = min(len(full_text), m.end() + 30)
            matches.append({
                "text": m.group(),
                "position": m.start(),
                "context": full_text[start:end],
            })
        return matches

    def replace_text(
        self,
        file_data: bytes,
        old_text: str,
        new_text: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
    ) -> tuple[bytes, int]:
        """Replace text in HWPX bytes. Returns (new_bytes, count)."""
        self._validate_zip_data(file_data)
        return self._replace_text_in_bytes(file_data, old_text, new_text, case_sensitive, use_regex)

    # ── HWP binary placeholder ──

    def convert_hwp_to_hwpx(self, file_data: bytes) -> bytes:
        """Convert HWP binary to HWPX. (Phase 2 - Java hwplib)"""
        raise HwpConversionError(
            "HWP 바이너리 파일 변환은 아직 지원되지 않습니다. "
            "HWPX 형식의 파일을 사용해 주세요."
        )

    # ── Internal methods ──

    @staticmethod
    def _validate_zip_data(file_data: bytes) -> None:
        """Validate that file_data is a valid ZIP archive."""
        if not file_data:
            raise HwpParseError("빈 파일 데이터입니다.")
        if not zipfile.is_zipfile(io.BytesIO(file_data)):
            raise HwpParseError("유효하지 않은 HWPX(ZIP) 파일입니다.")

    def _extract_text_from_bytes(self, file_data: bytes) -> str:
        """Extract all text from HWPX bytes."""
        texts: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_data), "r") as zf:
                for section_file in self._get_section_files(zf):
                    xml_data = zf.read(section_file)
                    root = SafeET.fromstring(xml_data)
                    for el in self._extract_text_elements(root):
                        texts.append(el.text)  # type: ignore[arg-type]
        except (zipfile.BadZipFile, ET.ParseError) as e:
            raise HwpParseError(f"HWPX 파일 파싱 실패: {e}")
        return "\n".join(texts)

    def _extract_tables_from_bytes(self, file_data: bytes) -> list[dict]:
        """Extract all tables from HWPX bytes."""
        tables: list[dict] = []
        table_index = 0
        try:
            with zipfile.ZipFile(io.BytesIO(file_data), "r") as zf:
                for section_file in self._get_section_files(zf):
                    xml_data = zf.read(section_file)
                    root = SafeET.fromstring(xml_data)
                    for el in root.iter():
                        if _get_local_name(el.tag) != "tbl":
                            continue
                        rows_data: list[list[str]] = []
                        for child in el:
                            if _get_local_name(child.tag) != "tr":
                                continue
                            row_cells: list[str] = []
                            for tc in child:
                                if _get_local_name(tc.tag) != "tc":
                                    continue
                                cell_text = "".join(
                                    t_el.text or ""
                                    for t_el in tc.iter()
                                    if _get_local_name(t_el.tag) == "t"
                                )
                                row_cells.append(cell_text)
                            if row_cells:
                                rows_data.append(row_cells)
                        if rows_data:
                            tables.append({
                                "index": table_index,
                                "rows": rows_data,
                                "headers": rows_data[0],
                            })
                            table_index += 1
        except (zipfile.BadZipFile, ET.ParseError) as e:
            raise HwpParseError(f"HWPX 테이블 추출 실패: {e}")
        return tables

    def _extract_metadata_from_bytes(self, file_data: bytes) -> dict:
        """Extract basic metadata from HWPX bytes."""
        metadata: dict = {"file_size": len(file_data), "section_count": 0}
        try:
            with zipfile.ZipFile(io.BytesIO(file_data), "r") as zf:
                sections = self._get_section_files(zf)
                metadata["section_count"] = len(sections)
                metadata["file_list"] = zf.namelist()
        except zipfile.BadZipFile:
            pass
        return metadata

    def _replace_text_in_bytes(
        self,
        file_data: bytes,
        old_text: str,
        new_text: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
    ) -> tuple[bytes, int]:
        """Replace text in HWPX bytes. Returns (new_bytes, count)."""
        total_replaced = 0
        buf_in = io.BytesIO(file_data)
        buf_out = io.BytesIO()

        try:
            with zipfile.ZipFile(buf_in, "r") as zf_in:
                section_files = set(self._get_section_files(zf_in))
                with zipfile.ZipFile(buf_out, "w", zipfile.ZIP_DEFLATED) as zf_out:
                    for item in zf_in.infolist():
                        data = zf_in.read(item.filename)
                        if item.filename in section_files:
                            root = SafeET.fromstring(data)
                            count = self._replace_in_element(
                                root, old_text, new_text, case_sensitive, use_regex
                            )
                            total_replaced += count
                            data = ET.tostring(
                                root, encoding="unicode", xml_declaration=True
                            ).encode("utf-8")
                        zf_out.writestr(item, data)
        except (zipfile.BadZipFile, ET.ParseError) as e:
            raise HwpParseError(f"HWPX 파일 수정 실패: {e}")

        return buf_out.getvalue(), total_replaced

    @staticmethod
    def _replace_in_element(
        element: ET.Element,
        old_text: str,
        new_text: str,
        case_sensitive: bool,
        use_regex: bool,
    ) -> int:
        """Replace text in XML element tree. Returns replacement count."""
        count = 0
        for t_elem in element.iter():
            if _get_local_name(t_elem.tag) != "t" or not t_elem.text:
                continue

            original = t_elem.text
            if use_regex:
                from app.services.search_service import _validate_regex
                _validate_regex(old_text)
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    new_val, n = re.subn(old_text, new_text, original, flags=flags)
                except re.error as e:
                    raise HwpServiceError(f"잘못된 정규식 패턴입니다: {e}")
            elif case_sensitive:
                n = original.count(old_text)
                new_val = original.replace(old_text, new_text)
            else:
                pattern = re.escape(old_text)
                new_val, n = re.subn(pattern, new_text, original, flags=re.IGNORECASE)

            if n > 0:
                t_elem.text = new_val
                count += n

        return count
