"""HWP/HWPX file processing service.

Provides a unified HwpService class for both HWP (binary) and HWPX (ZIP+XML) formats.

HWPX: Processed directly via XML parsing (ZIP archive with OWPML XML).
HWP:  Binary format requiring Java hwplib conversion (Phase 2).
"""

import os
import re
import shutil
import uuid
import zipfile
from xml.etree import ElementTree as ET

import aiofiles
import defusedxml.ElementTree as SafeET

from app.config import settings

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
    """Unified service for HWP/HWPX file processing."""

    # ── File storage helpers ──

    @staticmethod
    def get_document_dir(document_id: int) -> str:
        """Get the storage directory for a specific document."""
        return os.path.join(settings.UPLOAD_DIR, str(document_id))

    @staticmethod
    def get_versions_dir(document_id: int) -> str:
        return os.path.join(settings.UPLOAD_DIR, str(document_id), "versions")

    @staticmethod
    def ensure_document_dirs(document_id: int) -> None:
        """Create the directory structure for a document."""
        doc_dir = HwpService.get_document_dir(document_id)
        versions_dir = HwpService.get_versions_dir(document_id)
        os.makedirs(doc_dir, exist_ok=True)
        os.makedirs(versions_dir, exist_ok=True)

    # ── Upload / Save to disk ──

    @staticmethod
    async def save_upload_to_temp(file_content: bytes, ext: str) -> str:
        """Save uploaded bytes to a temp file, returns temp path."""
        temp_dir = os.path.join(settings.UPLOAD_DIR, "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}{ext}")
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(file_content)
        return temp_path

    @staticmethod
    def move_to_document_storage(
        temp_path: str, document_id: int, ext: str
    ) -> tuple[str, str]:
        """Move temp file into structured storage.

        Returns (original_path, current_path).
        Structure:
            uploads/{document_id}/original.hwpx
            uploads/{document_id}/current.hwpx
            uploads/{document_id}/versions/v1.hwpx
        """
        HwpService.ensure_document_dirs(document_id)
        doc_dir = HwpService.get_document_dir(document_id)
        versions_dir = HwpService.get_versions_dir(document_id)

        original_path = os.path.join(doc_dir, f"original{ext}")
        current_path = os.path.join(doc_dir, f"current{ext}")
        v1_path = os.path.join(versions_dir, f"v1{ext}")

        shutil.copy2(temp_path, original_path)
        shutil.copy2(temp_path, current_path)
        shutil.copy2(temp_path, v1_path)

        # Clean up temp
        os.remove(temp_path)

        return original_path, current_path

    @staticmethod
    def save_version_file(
        source_path: str, document_id: int, version_number: int, ext: str
    ) -> str:
        """Copy a file as a new version. Returns version file path."""
        versions_dir = HwpService.get_versions_dir(document_id)
        os.makedirs(versions_dir, exist_ok=True)
        version_path = os.path.join(versions_dir, f"v{version_number}{ext}")
        shutil.copy2(source_path, version_path)
        return version_path

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

    # ── Core API ──

    async def parse_file(self, file_path: str) -> dict:
        """Parse an HWPX file and extract text, tables, and metadata.

        Returns: {"text": str, "tables": list[dict], "metadata": dict}
        """
        self._ensure_hwpx(file_path)
        self._validate_zip(file_path)

        text = self._extract_text_sync(file_path)
        tables = self._extract_tables_sync(file_path)
        metadata = self._extract_metadata(file_path)

        return {
            "text": text,
            "tables": tables,
            "metadata": metadata,
        }

    async def extract_tables(self, file_path: str) -> list[dict]:
        """Extract all tables from an HWPX file.

        Each table: {"index": int, "rows": list[list[str]], "headers": list[str]}
        """
        self._ensure_hwpx(file_path)
        self._validate_zip(file_path)
        return self._extract_tables_sync(file_path)

    async def update_content(self, file_path: str, changes: dict) -> str:
        """Apply text/table changes and save as new file.

        Args:
            file_path: Path to the current HWPX file.
            changes: {"replacements": [{"old": str, "new": str}]}

        Returns: Path to the modified HWPX file.
        """
        self._ensure_hwpx(file_path)
        self._validate_zip(file_path)

        replacements = changes.get("replacements", [])
        current_path = file_path

        for r in replacements:
            new_path, _ = self._replace_text_sync(
                current_path, r["old"], r["new"],
                case_sensitive=r.get("case_sensitive", True),
                use_regex=r.get("regex", False),
            )
            current_path = new_path

        return current_path

    async def get_text_content(self, file_path: str) -> str:
        """Extract full text content for editor display."""
        self._ensure_hwpx(file_path)
        self._validate_zip(file_path)
        return self._extract_text_sync(file_path)

    async def save_file(self, file_path: str, content: str) -> str:
        """Save modified text content back to an HWPX file.

        This replaces all text in the file with the provided content,
        preserving the XML structure and non-text elements.

        Returns: Path to the saved file.
        """
        self._ensure_hwpx(file_path)
        self._validate_zip(file_path)

        dir_name = os.path.dirname(file_path)
        new_path = os.path.join(dir_name, f"{uuid.uuid4().hex}.hwpx")

        # Split new content into lines to distribute across text elements
        new_lines = content.split("\n")
        line_idx = 0

        with zipfile.ZipFile(file_path, "r") as zf_in:
            section_files = set(self._get_section_files(zf_in))

            with zipfile.ZipFile(new_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
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

        return new_path

    # ── Search / Replace ──

    def search_text(
        self,
        file_path: str,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> list[dict]:
        """Search for text occurrences in a file."""
        self._ensure_hwpx(file_path)
        from app.services.search_service import _validate_regex

        full_text = self._extract_text_sync(file_path)
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
        file_path: str,
        old_text: str,
        new_text: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
    ) -> tuple[str, int]:
        """Replace text in an HWPX file.

        Returns (new_file_path, replacement_count).
        """
        self._ensure_hwpx(file_path)
        return self._replace_text_sync(file_path, old_text, new_text, case_sensitive, use_regex)

    # ── HWP binary placeholder ──

    def convert_hwp_to_hwpx(self, file_path: str, output_dir: str | None = None) -> str:
        """Convert HWP binary to HWPX. (Phase 2 - Java hwplib)"""
        raise HwpConversionError(
            "HWP 바이너리 파일 변환은 아직 지원되지 않습니다. "
            "HWPX 형식의 파일을 사용해 주세요. "
            "(HWP 지원은 Phase 2에서 Java hwplib 연동으로 구현 예정)"
        )

    # ── Internal sync methods ──

    def _ensure_hwpx(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".hwp":
            raise HwpConversionError(
                "HWP 바이너리 파일은 아직 지원되지 않습니다. "
                "HWPX 형식의 파일을 사용해 주세요."
            )

    @staticmethod
    def _validate_zip(file_path: str) -> None:
        if not zipfile.is_zipfile(file_path):
            raise HwpParseError(f"유효하지 않은 HWPX(ZIP) 파일입니다: {file_path}")

    def _extract_text_sync(self, file_path: str) -> str:
        texts: list[str] = []
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for section_file in self._get_section_files(zf):
                    xml_data = zf.read(section_file)
                    root = SafeET.fromstring(xml_data)
                    for el in self._extract_text_elements(root):
                        texts.append(el.text)  # type: ignore[arg-type]
        except (zipfile.BadZipFile, ET.ParseError) as e:
            raise HwpParseError(f"HWPX 파일 파싱 실패: {e}")
        return "\n".join(texts)

    def _extract_tables_sync(self, file_path: str) -> list[dict]:
        tables: list[dict] = []
        table_index = 0

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
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
                            headers = rows_data[0] if rows_data else []
                            tables.append({
                                "index": table_index,
                                "rows": rows_data,
                                "headers": headers,
                            })
                            table_index += 1

        except (zipfile.BadZipFile, ET.ParseError) as e:
            raise HwpParseError(f"HWPX 테이블 추출 실패: {e}")

        return tables

    def _extract_metadata(self, file_path: str) -> dict:
        """Extract basic metadata from HWPX file."""
        metadata: dict = {
            "file_size": os.path.getsize(file_path),
            "section_count": 0,
        }
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                sections = self._get_section_files(zf)
                metadata["section_count"] = len(sections)
                metadata["file_list"] = zf.namelist()
        except zipfile.BadZipFile:
            pass
        return metadata

    def _replace_text_sync(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
    ) -> tuple[str, int]:
        """Replace text in HWPX file. Returns (new_path, count)."""
        dir_name = os.path.dirname(file_path)
        new_file_path = os.path.join(dir_name, f"{uuid.uuid4().hex}.hwpx")
        total_replaced = 0

        try:
            with zipfile.ZipFile(file_path, "r") as zf_in:
                section_files = set(self._get_section_files(zf_in))

                with zipfile.ZipFile(new_file_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
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

        return new_file_path, total_replaced

    @staticmethod
    def _replace_in_element(
        element: ET.Element,
        old_text: str,
        new_text: str,
        case_sensitive: bool,
        use_regex: bool,
    ) -> int:
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
