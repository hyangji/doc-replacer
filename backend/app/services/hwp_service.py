"""HWP/HWPX file processing service.

Provides a unified HwpService class for both HWP (binary) and HWPX (ZIP+XML) formats.
All file operations work with in-memory bytes (no local file system dependency).
"""

import io
import os
import re
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as SafeET
import olefile

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

    async def parse_file(self, file_data: bytes, file_type: str = "hwpx") -> dict:
        """Parse an HWP/HWPX file and extract text, tables, and metadata.

        Returns: {"text": str, "tables": list[dict], "metadata": dict}
        """
        if file_type == "hwp":
            self._validate_ole_data(file_data)
            text = self._extract_text_from_hwp_bytes(file_data)
            tables = self._extract_tables_from_hwp_bytes(file_data)
            metadata = {"file_size": len(file_data), "format": "hwp"}
        else:
            self._validate_zip_data(file_data)
            text = self._extract_text_from_bytes(file_data)
            tables = self._extract_tables_from_bytes(file_data)
            metadata = self._extract_metadata_from_bytes(file_data)
        return {"text": text, "tables": tables, "metadata": metadata}

    async def extract_tables(self, file_data: bytes, file_type: str = "hwpx") -> list[dict]:
        """Extract all tables from an HWP/HWPX file.

        Each table: {"index": int, "rows": list[list[str]], "headers": list[str]}
        """
        if file_type == "hwp":
            self._validate_ole_data(file_data)
            return self._extract_tables_from_hwp_bytes(file_data)
        self._validate_zip_data(file_data)
        return self._extract_tables_from_bytes(file_data)

    async def get_text_content(self, file_data: bytes, file_type: str = "hwpx") -> str:
        """Extract full text content for editor display."""
        if file_type == "hwp":
            self._validate_ole_data(file_data)
            return self._extract_text_from_hwp_bytes(file_data)
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
        file_type: str = "hwpx",
    ) -> list[dict]:
        """Search for text occurrences in file data."""
        from app.services.search_service import _validate_regex

        if file_type == "hwp":
            full_text = self._extract_text_from_hwp_bytes(file_data)
        else:
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
        file_type: str = "hwpx",
    ) -> tuple[bytes, int]:
        """Replace text in HWP/HWPX bytes. Returns (new_bytes, count)."""
        if file_type == "hwp":
            self._validate_ole_data(file_data)
            return self._replace_text_in_hwp_bytes(
                file_data, old_text, new_text, case_sensitive, use_regex
            )
        self._validate_zip_data(file_data)
        return self._replace_text_in_bytes(file_data, old_text, new_text, case_sensitive, use_regex)

    # ── HWP binary support ──

    def convert_hwp_to_hwpx(self, file_data: bytes) -> bytes:
        """Convert HWP binary to HWPX. (Phase 2 - Java hwplib)"""
        raise HwpConversionError(
            "HWP 바이너리 파일 변환은 아직 지원되지 않습니다. "
            "HWPX 형식의 파일을 사용해 주세요."
        )

    # ── HWP binary parsing (read-only) ──

    @staticmethod
    def _is_hwp_compressed(file_data: bytes) -> bool:
        """Check if HWP binary file uses compression."""
        ole = olefile.OleFileIO(io.BytesIO(file_data))
        try:
            header = ole.openstream("FileHeader").read()
            if len(header) >= 40:
                props = struct.unpack_from("<I", header, 36)[0]
                return bool(props & 1)
            return False
        finally:
            ole.close()

    @staticmethod
    def _parse_hwp_para_text(text_data: bytes) -> str:
        """Parse a HWPTAG_PARA_TEXT record into a string.

        HWP stores text as UTF-16LE with inline control characters (0-31).
        Control chars 1-31 (except 0,10,13) carry 14 extra bytes of inline data.
        """
        text = ""
        i = 0
        while i < len(text_data) - 1:
            ch = struct.unpack_from("<H", text_data, i)[0]
            i += 2
            if ch < 32:
                if ch not in (0, 10, 13):
                    # Extended control characters have 14-byte inline payload
                    i += 14
            else:
                text += chr(ch)
        return text

    def _extract_text_from_hwp_bytes(self, file_data: bytes) -> str:
        """Extract all text from HWP binary (OLE2) bytes."""
        texts: list[str] = []
        try:
            ole = olefile.OleFileIO(io.BytesIO(file_data))
        except Exception as e:
            raise HwpParseError(f"HWP 파일 열기 실패: {e}")

        try:
            compressed = self._is_hwp_compressed(file_data)

            # Find all BodyText/SectionN streams
            section_streams = [
                "/".join(entry)
                for entry in ole.listdir()
                if len(entry) == 2
                and entry[0] == "BodyText"
                and entry[1].startswith("Section")
            ]
            section_streams.sort()

            for stream_path in section_streams:
                raw = ole.openstream(stream_path).read()
                if compressed:
                    try:
                        data = zlib.decompress(raw, -15)
                    except zlib.error as e:
                        raise HwpParseError(f"HWP 섹션 압축 해제 실패: {e}")
                else:
                    data = raw

                # Walk HWP binary records
                pos = 0
                while pos < len(data):
                    if pos + 4 > len(data):
                        break
                    tag_data = struct.unpack_from("<I", data, pos)[0]
                    tag_id = tag_data & 0x3FF
                    size = (tag_data >> 20) & 0xFFF
                    pos += 4

                    # Extended size (> 4095 bytes)
                    if size == 0xFFF:
                        if pos + 4 > len(data):
                            break
                        size = struct.unpack_from("<I", data, pos)[0]
                        pos += 4

                    if tag_id == 67:  # HWPTAG_PARA_TEXT
                        para_text = self._parse_hwp_para_text(data[pos : pos + size])
                        if para_text.strip():
                            texts.append(para_text.strip())

                    pos += size
        finally:
            ole.close()

        return "\n".join(texts)

    def _extract_tables_from_hwp_bytes(self, file_data: bytes) -> list[dict]:
        """Extract tables from HWP binary file.

        HWP 5.0 tag IDs (HWPTAG_BEGIN=16):
          HWPTAG_TABLE = 77, HWPTAG_LIST_HEADER = 72, HWPTAG_PARA_TEXT = 67

        Each table consists of a TABLE record followed by LIST_HEADER records
        (one per cell). Cell text is in PARA_TEXT records at a deeper level.
        """
        # Tag ID constants
        TAG_PARA_TEXT = 67
        TAG_LIST_HEADER = 72
        TAG_TABLE = 77

        tables: list[dict] = []
        try:
            ole = olefile.OleFileIO(io.BytesIO(file_data))
        except Exception as e:
            raise HwpParseError(f"HWP 파일 열기 실패: {e}")

        try:
            compressed = self._is_hwp_compressed(file_data)

            section_streams = [
                "/".join(entry)
                for entry in ole.listdir()
                if len(entry) == 2
                and entry[0] == "BodyText"
                and entry[1].startswith("Section")
            ]
            section_streams.sort()

            table_index = 0
            for stream_path in section_streams:
                raw = ole.openstream(stream_path).read()
                if compressed:
                    try:
                        data = zlib.decompress(raw, -15)
                    except zlib.error:
                        continue
                else:
                    data = raw

                # First pass: collect all records
                records: list[tuple[int, int, int, bytes]] = []
                pos = 0
                while pos < len(data):
                    if pos + 4 > len(data):
                        break
                    tag_data = struct.unpack_from("<I", data, pos)[0]
                    tag_id = tag_data & 0x3FF
                    level = (tag_data >> 10) & 0x3FF
                    size = (tag_data >> 20) & 0xFFF
                    pos += 4

                    if size == 0xFFF:
                        if pos + 4 > len(data):
                            break
                        size = struct.unpack_from("<I", data, pos)[0]
                        pos += 4

                    payload = data[pos : pos + size]
                    records.append((tag_id, level, size, payload))
                    pos += size

                # Second pass: find TABLE records and collect cell text
                i = 0
                while i < len(records):
                    tag_id, level, size, payload = records[i]

                    if tag_id == TAG_TABLE:
                        # TABLE record: [4 bytes attr][2 bytes nRows][2 bytes nCols]...
                        if len(payload) >= 8:
                            n_rows = struct.unpack_from("<H", payload, 4)[0]
                            n_cols = struct.unpack_from("<H", payload, 6)[0]
                        else:
                            n_rows, n_cols = 0, 0

                        table_level = level
                        cell_texts: list[str] = []

                        # Walk subsequent records belonging to this table
                        j = i + 1
                        while j < len(records):
                            t_id, t_level, _, t_payload = records[j]
                            # Records at shallower level than the table = outside
                            if t_level < table_level:
                                break
                            # Another TABLE at same level = next table
                            if t_id == TAG_TABLE and t_level == table_level:
                                break

                            if t_id == TAG_LIST_HEADER and t_level == table_level:
                                # New cell boundary
                                cell_texts.append("")
                            elif t_id == TAG_PARA_TEXT and t_level > table_level:
                                para = self._parse_hwp_para_text(t_payload)
                                if cell_texts and para.strip():
                                    if cell_texts[-1]:
                                        cell_texts[-1] += " " + para.strip()
                                    else:
                                        cell_texts[-1] = para.strip()

                            j += 1

                        # Reconstruct rows from flat cell list using nCols
                        if n_cols > 0 and cell_texts:
                            rows_data: list[list[str]] = []
                            for r_idx in range(0, len(cell_texts), n_cols):
                                row = cell_texts[r_idx : r_idx + n_cols]
                                while len(row) < n_cols:
                                    row.append("")
                                rows_data.append(row)

                            if rows_data:
                                tables.append({
                                    "index": table_index,
                                    "rows": rows_data,
                                    "headers": rows_data[0],
                                })
                                table_index += 1

                        i = j
                        continue

                    i += 1
        finally:
            ole.close()

        return tables

    # ── HWP binary text replacement ──

    @staticmethod
    def _build_hwp_para_text(text_data: bytes, old_text: str, new_text: str,
                              case_sensitive: bool, use_regex: bool) -> tuple[bytes, int]:
        """Replace text within a HWPTAG_PARA_TEXT record payload.

        Preserves all control characters and their 14-byte inline payloads.
        Only modifies the printable text portions.
        Returns (new_payload_bytes, replacement_count).
        """
        # Split the payload into segments: (is_text, data)
        segments: list[tuple[bool, bytes]] = []
        text_chars: list[str] = []
        i = 0
        while i < len(text_data) - 1:
            ch = struct.unpack_from("<H", text_data, i)[0]
            if ch < 32:
                # Flush accumulated text
                if text_chars:
                    segments.append((True, "".join(text_chars).encode("utf-16-le")))
                    text_chars = []
                if ch in (0, 10, 13):
                    # Simple control: just the 2-byte char
                    segments.append((False, text_data[i:i + 2]))
                    i += 2
                else:
                    # Extended control: 2-byte char + 14-byte payload
                    segments.append((False, text_data[i:i + 16]))
                    i += 16
            else:
                text_chars.append(chr(ch))
                i += 2

        if text_chars:
            segments.append((True, "".join(text_chars).encode("utf-16-le")))

        # Perform replacement on text segments
        total_count = 0
        new_segments: list[bytes] = []
        for is_text, seg_data in segments:
            if not is_text:
                new_segments.append(seg_data)
                continue

            original = seg_data.decode("utf-16-le")
            if use_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                new_val, n = re.subn(old_text, new_text, original, flags=flags)
            elif case_sensitive:
                n = original.count(old_text)
                new_val = original.replace(old_text, new_text)
            else:
                pattern = re.escape(old_text)
                new_val, n = re.subn(pattern, new_text, original, flags=re.IGNORECASE)

            total_count += n
            new_segments.append(new_val.encode("utf-16-le"))

        return b"".join(new_segments), total_count

    @staticmethod
    def _build_record_header(tag_id: int, level: int, size: int) -> bytes:
        """Build a HWP binary record header (4 bytes, optionally + 4 bytes extended size)."""
        if size >= 0xFFF:
            tag_data = tag_id | (level << 10) | (0xFFF << 20)
            return struct.pack("<II", tag_data, size)
        else:
            tag_data = tag_id | (level << 10) | (size << 20)
            return struct.pack("<I", tag_data)

    def _replace_text_in_hwp_bytes(
        self,
        file_data: bytes,
        old_text: str,
        new_text: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
    ) -> tuple[bytes, int]:
        """Replace text in HWP binary bytes. Returns (new_bytes, count).

        Process: decompress section → walk records → replace in PARA_TEXT →
                 rebuild records → recompress → write back to OLE2.
        """
        total_replaced = 0
        # OleFileIO modifies data in the underlying file object in-place
        buf = io.BytesIO(bytearray(file_data))  # mutable copy
        try:
            ole = olefile.OleFileIO(buf, write_mode=True)
        except Exception as e:
            raise HwpParseError(f"HWP 파일 열기 실패: {e}")

        try:
            compressed = self._is_hwp_compressed(file_data)

            section_streams = sorted(
                "/".join(entry)
                for entry in ole.listdir()
                if len(entry) == 2
                and entry[0] == "BodyText"
                and entry[1].startswith("Section")
            )

            for stream_path in section_streams:
                raw = ole.openstream(stream_path).read()
                if compressed:
                    try:
                        data = zlib.decompress(raw, -15)
                    except zlib.error as e:
                        raise HwpParseError(f"HWP 섹션 압축 해제 실패: {e}")
                else:
                    data = raw

                # Parse all records
                records: list[tuple[int, int, bytes]] = []  # (tag_id, level, payload)
                pos = 0
                while pos < len(data):
                    if pos + 4 > len(data):
                        break
                    tag_data_val = struct.unpack_from("<I", data, pos)[0]
                    tag_id = tag_data_val & 0x3FF
                    level = (tag_data_val >> 10) & 0x3FF
                    size = (tag_data_val >> 20) & 0xFFF
                    pos += 4

                    if size == 0xFFF:
                        if pos + 4 > len(data):
                            break
                        size = struct.unpack_from("<I", data, pos)[0]
                        pos += 4

                    payload = data[pos:pos + size]
                    records.append((tag_id, level, payload))
                    pos += size

                # Replace text in PARA_TEXT records
                section_count = 0
                new_records: list[tuple[int, int, bytes]] = []
                for tag_id, level, payload in records:
                    if tag_id == 67 and len(payload) >= 2:  # HWPTAG_PARA_TEXT
                        new_payload, n = self._build_hwp_para_text(
                            payload, old_text, new_text, case_sensitive, use_regex
                        )
                        section_count += n
                        new_records.append((tag_id, level, new_payload))
                    else:
                        new_records.append((tag_id, level, payload))

                if section_count > 0:
                    total_replaced += section_count

                    # Rebuild section binary
                    parts: list[bytes] = []
                    for tag_id, level, payload in new_records:
                        parts.append(self._build_record_header(tag_id, level, len(payload)))
                        parts.append(payload)
                    new_data = b"".join(parts)

                    # Recompress if needed, matching original stream size
                    original_size = len(raw)
                    if compressed:
                        # Try compression levels to fit within original size
                        new_raw = None
                        for comp_level in (zlib.Z_DEFAULT_COMPRESSION, 9, 6, 3, 1, 0):
                            compressor = zlib.compressobj(comp_level, zlib.DEFLATED, -15)
                            candidate = compressor.compress(new_data) + compressor.flush()
                            if len(candidate) <= original_size:
                                # Pad to exact original size (trailing bytes ignored by decompressor)
                                new_raw = candidate + b"\x00" * (original_size - len(candidate))
                                break
                        if new_raw is None:
                            # Compressed output too large even at level 0 - can't fit
                            raise HwpParseError(
                                "교체 텍스트가 너무 길어 원본 HWP 파일에 저장할 수 없습니다. "
                                "교체 텍스트를 줄이거나 HWPX 형식을 사용해 주세요."
                            )
                    else:
                        new_raw = new_data

                    ole.write_stream(stream_path, new_raw)

            # After write_stream, modifications are in the underlying BytesIO
            result = None  # will be set after close
        except HwpParseError:
            raise
        except Exception as e:
            raise HwpParseError(f"HWP 파일 수정 실패: {e}")
        finally:
            ole.close()

        result = buf.getvalue()
        return result, total_replaced

    # ── Internal methods ──

    @staticmethod
    def _validate_zip_data(file_data: bytes) -> None:
        """Validate that file_data is a valid ZIP archive."""
        if not file_data:
            raise HwpParseError("빈 파일 데이터입니다.")
        if not zipfile.is_zipfile(io.BytesIO(file_data)):
            raise HwpParseError("유효하지 않은 HWPX(ZIP) 파일입니다.")

    @staticmethod
    def _validate_ole_data(file_data: bytes) -> None:
        """Validate that file_data is a valid OLE2 (HWP binary) file."""
        if not file_data:
            raise HwpParseError("빈 파일 데이터입니다.")
        if not olefile.isOleFile(io.BytesIO(file_data)):
            raise HwpParseError("유효하지 않은 HWP 바이너리 파일입니다.")

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
