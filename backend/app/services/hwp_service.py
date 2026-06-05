"""HWP/HWPX file processing service.

Provides a unified HwpService class for both HWP (binary) and HWPX (ZIP+XML) formats.
All file operations work with in-memory bytes (no local file system dependency).
"""

import difflib
import html
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
                              case_sensitive: bool, use_regex: bool
                              ) -> tuple[bytes, int, int, int]:
        """Replace text within a HWPTAG_PARA_TEXT record payload.

        Preserves all control characters and their 14-byte inline payloads.
        Only modifies the printable text portions.

        Returns (new_payload_bytes, replacement_count, first_edit_pos, delta) where:
          - first_edit_pos: the paragraph char-position (WCHAR units) of the first
            position whose content/offset changed (i.e. where the first replacement
            began). -1 if nothing changed.
          - delta: net change in paragraph length, in WCHAR position units
            (printable chars are 1 position each). Positive = paragraph grew.

        HWP position units: a printable WCHAR = 1 position; a simple control char
        (0/10/13) = 1 position; an extended control char = 8 positions (1 for the
        control word + 7 for its 14-byte inline payload). Replacements only happen
        inside printable text segments, so `first_edit_pos` is computed by summing the
        positions of all preceding segments plus the in-segment match offset.
        """
        # Split the payload into segments: (is_text, data, start_pos)
        # start_pos = paragraph char-position (WCHAR units) where this segment begins.
        segments: list[tuple[bool, bytes, int]] = []
        text_chars: list[str] = []
        seg_start = 0  # position where the current text run started
        cur_pos = 0    # running paragraph position counter
        i = 0
        while i < len(text_data) - 1:
            ch = struct.unpack_from("<H", text_data, i)[0]
            if ch < 32:
                # Flush accumulated text
                if text_chars:
                    segments.append((True, "".join(text_chars).encode("utf-16-le"), seg_start))
                    text_chars = []
                if ch in (0, 10, 13):
                    # Simple control: just the 2-byte char, occupies 1 position
                    segments.append((False, text_data[i:i + 2], cur_pos))
                    i += 2
                    cur_pos += 1
                else:
                    # Extended control: 2-byte char + 14-byte payload, occupies 8 positions
                    segments.append((False, text_data[i:i + 16], cur_pos))
                    i += 16
                    cur_pos += 8
                seg_start = cur_pos
            else:
                if not text_chars:
                    seg_start = cur_pos
                text_chars.append(chr(ch))
                i += 2
                cur_pos += 1

        if text_chars:
            segments.append((True, "".join(text_chars).encode("utf-16-le"), seg_start))

        # Perform replacement on text segments, tracking first edit position and delta.
        total_count = 0
        delta = 0
        first_edit_pos = -1
        new_segments: list[bytes] = []
        for is_text, seg_data, start_pos in segments:
            if not is_text:
                new_segments.append(seg_data)
                continue

            original = seg_data.decode("utf-16-le")
            if use_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(old_text, flags)
            elif case_sensitive:
                pattern = re.compile(re.escape(old_text))
            else:
                pattern = re.compile(re.escape(old_text), re.IGNORECASE)

            # Use finditer so we know the in-segment offset of the first match
            # (needed for first_edit_pos). Then perform the substitution.
            first_match = pattern.search(original)
            new_val, n = pattern.subn(new_text, original)
            if n > 0:
                if first_edit_pos == -1 and first_match is not None:
                    first_edit_pos = start_pos + first_match.start()
                delta += len(new_val) - len(original)
                total_count += n

            new_segments.append(new_val.encode("utf-16-le"))

        return b"".join(new_segments), total_count, first_edit_pos, delta

    @staticmethod
    def _count_para_text_positions(text_data: bytes) -> int:
        """Count paragraph char-positions (WCHAR units) in a PARA_TEXT payload.

        Printable WCHAR = 1 position; simple control (0/10/13) = 1; extended
        control = 8 (1 control word + 7 for its 14-byte inline payload).
        """
        pos_count = 0
        i = 0
        while i < len(text_data) - 1:
            ch = struct.unpack_from("<H", text_data, i)[0]
            i += 2
            if ch < 32:
                if ch in (0, 10, 13):
                    pos_count += 1
                else:
                    i += 14
                    pos_count += 8
            else:
                pos_count += 1
        return pos_count

    @staticmethod
    def _patch_para_header_nchars(payload: bytes, delta: int) -> bytes:
        """Adjust HWPTAG_PARA_HEADER nChars by `delta` (WCHAR positions).

        nChars is stored in the low 31 bits of the first UINT32; the top bit
        (0x80000000) is a flag that must be preserved verbatim. (Measured against
        the sample: u32[0] & 0x7FFFFFFF == PARA_TEXT position count for every para.)
        """
        if len(payload) < 4 or delta == 0:
            return payload
        raw = struct.unpack_from("<I", payload, 0)[0]
        flag = raw & 0x80000000
        nchars = raw & 0x7FFFFFFF
        new_nchars = max(0, nchars + delta) & 0x7FFFFFFF
        out = bytearray(payload)
        struct.pack_into("<I", out, 0, flag | new_nchars)
        return bytes(out)

    @staticmethod
    def _patch_char_shape_positions(payload: bytes, edit_pos: int, delta: int) -> bytes:
        """Shift HWPTAG_PARA_CHAR_SHAPE entry positions after an edit.

        Layout: array of (UINT32 charPos, UINT32 charShapeId), stride 8.
        Every entry whose charPos > edit_pos is shifted by `delta`. The first entry
        (charPos 0) and any entry at/before the edit position keep their position so
        the run-style boundaries stay anchored to the edited text's start.
        """
        if delta == 0 or len(payload) < 8 or edit_pos < 0:
            return payload
        out = bytearray(payload)
        n_entries = len(payload) // 8
        for k in range(n_entries):
            off = k * 8
            char_pos = struct.unpack_from("<I", out, off)[0]
            if char_pos > edit_pos:
                new_pos = max(0, char_pos + delta) & 0xFFFFFFFF
                struct.pack_into("<I", out, off, new_pos)
        return bytes(out)

    @staticmethod
    def _patch_line_seg_positions(payload: bytes, edit_pos: int, delta: int) -> bytes:
        """Shift HWPTAG_PARA_LINE_SEG segment start positions after an edit.

        Layout: array of LineSeg structs, stride 36 bytes. The first INT32 of each
        struct is the segment's starting char-position (textpos) within the paragraph.
        Each segment whose start textpos > edit_pos is shifted by `delta`. The segment
        containing the edit keeps its start (its char-count grows/shrinks implicitly
        as the following segment start moves). Hancom relays out lines on open, so the
        glyph count per line is recomputed; keeping start positions monotonic and in
        range is what matters to avoid the corruption warning.
        """
        STRIDE = 36
        if delta == 0 or edit_pos < 0 or len(payload) < STRIDE:
            return payload
        out = bytearray(payload)
        n_seg = len(payload) // STRIDE
        for k in range(n_seg):
            off = k * STRIDE
            start = struct.unpack_from("<i", out, off)[0]
            if start > edit_pos:
                struct.pack_into("<i", out, off, max(0, start + delta))
        return bytes(out)

    @staticmethod
    def _build_record_header(tag_id: int, level: int, size: int) -> bytes:
        """Build a HWP binary record header (4 bytes, optionally + 4 bytes extended size)."""
        if size >= 0xFFF:
            tag_data = tag_id | (level << 10) | (0xFFF << 20)
            return struct.pack("<II", tag_data, size)
        else:
            tag_data = tag_id | (level << 10) | (size << 20)
            return struct.pack("<I", tag_data)

    @staticmethod
    def _decode_section_stream(raw: bytes) -> tuple[bytes, bytes]:
        """Decompress a raw-deflate HWP section stream and split off any trailer.

        Some HWP producers append an 8-byte trailer after the raw deflate data:
            trailer = crc32(decompressed) [u32 LE] + len(decompressed) [u32 LE]
        Standard HWP 5.0 has no trailer (trailing bytes == b"").

        Returns (decompressed_bytes, trailer_bytes). The trailer is returned verbatim
        so the original stream layout (deflate + trailer) can be reproduced exactly.
        """
        d = zlib.decompressobj(-15)
        out = d.decompress(raw)
        out += d.flush()
        return out, d.unused_data

    @staticmethod
    def _make_stored_block(payload: bytes, final: bool) -> bytes:
        """Build a single DEFLATE 'stored' (uncompressed) block, byte-aligned.

        Header byte: BFINAL=bit0, BTYPE=00 (stored). Then LEN (u16 LE) and NLEN (~LEN).
        An empty stored block (LEN=0) emits zero output bytes; a non-empty one emits its
        literal payload. Used for byte-precise length padding without corrupting output.
        """
        b0 = 0x01 if final else 0x00
        ln = len(payload) & 0xFFFF
        return bytes([b0]) + struct.pack("<HH", ln, (~ln) & 0xFFFF) + payload

    @classmethod
    def _build_section_stream(
        cls, new_data: bytes, target_size: int, trailer: bytes
    ) -> bytes | None:
        """Re-encode a decompressed section into a raw-deflate stream of an EXACT size.

        olefile's write_stream requires the new stream to match the original stream size
        byte-for-byte. We must therefore emit a stream of exactly `target_size` bytes whose
        decompression equals `new_data` and whose post-deflate trailer equals `trailer`
        (recomputed by the caller). Critically, after decompression the leftover bytes
        (decompressobj.unused_data) must be EXACTLY `trailer` with no zero padding, or
        Hancom flags the document as corrupted/tampered.

        Technique (valid-deflate padding):
          1. Compress head = new_data[:-tail] and Z_SYNC_FLUSH (byte-aligned, non-final).
          2. Emit the last `tail` bytes as one literal stored block (output preserved).
          3. Pad to the exact deflate length with empty (zero-output) stored blocks;
             the final block carries BFINAL=1 to terminate the stream cleanly.
          We scan `tail` so the remaining pad is a non-negative multiple of 5 (each empty
          stored block is exactly 5 bytes), giving byte-precise control over total length.

        Returns the exact-size stream bytes, or None if even the smallest valid encoding
        exceeds `target_size` (caller must handle the overflow case).
        """
        target_deflate = target_size - len(trailer)
        if target_deflate < 5:
            return None

        # Quick feasibility check: natural (minimal) deflate must fit.
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        minimal = co.compress(new_data) + co.flush()
        if len(minimal) > target_deflate:
            return None

        empty_nonfinal = cls._make_stored_block(b"", False)
        empty_final = cls._make_stored_block(b"", True)

        n = len(new_data)
        # tail==0 path: just empty-block padding after a sync-flushed body.
        candidates = [0] + list(range(1, min(n, 8192) + 1))
        for tail in candidates:
            head = new_data[: n - tail] if tail else new_data
            co = zlib.compressobj(9, zlib.DEFLATED, -15)
            body = co.compress(head) + co.flush(zlib.Z_SYNC_FLUSH)
            if tail:
                body += cls._make_stored_block(new_data[n - tail:], False)
            pad = target_deflate - len(body)
            if pad >= 5 and pad % 5 == 0:
                body += empty_nonfinal * (pad // 5 - 1) + empty_final
                if len(body) == target_deflate:
                    return body + trailer
        return None

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
                trailer = b""
                if compressed:
                    try:
                        data, trailer = self._decode_section_stream(raw)
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

                # Replace text in PARA_TEXT records, paragraph by paragraph.
                # Each paragraph is a group of sibling records:
                #   PARA_HEADER(66) → PARA_TEXT(67) → CHAR_SHAPE(68) → LINE_SEG(69)
                # When a PARA_TEXT replacement changes the paragraph length (delta!=0),
                # the sibling PARA_HEADER nChars, CHAR_SHAPE positions and LINE_SEG
                # starts in the SAME group must be adjusted so the metadata stays in
                # sync with the new text (otherwise Hancom reports corruption).
                TAG_PARA_HEADER = 66
                TAG_PARA_TEXT = 67
                TAG_PARA_CHAR_SHAPE = 68
                TAG_PARA_LINE_SEG = 69

                section_count = 0
                # new_records is mutable so we can back-patch the PARA_HEADER (which
                # precedes the PARA_TEXT) once the delta is known.
                new_records: list[list] = [[t, l, p] for (t, l, p) in records]

                # header_idx tracks the most recent PARA_HEADER position so its
                # nChars can be patched after the PARA_TEXT in the same group.
                header_idx = -1
                # Per-group edit state (set by PARA_TEXT, consumed by 68/69 siblings).
                #   group_edit_pos: earliest paragraph-global char-position edited.
                #   group_delta:    accumulated length change for the whole paragraph.
                #   group_text_base: paragraph-global position where the *current*
                #                    PARA_TEXT record begins (supports the rare case of
                #                    multiple PARA_TEXT records inside one paragraph).
                group_edit_pos = -1
                group_delta = 0
                group_text_base = 0
                for r_idx in range(len(new_records)):
                    tag_id, level, payload = new_records[r_idx]

                    if tag_id == TAG_PARA_HEADER:
                        header_idx = r_idx
                        group_edit_pos = -1
                        group_delta = 0
                        group_text_base = 0
                    elif tag_id == TAG_PARA_TEXT and len(payload) >= 2:
                        new_payload, n, edit_pos, delta = self._build_hwp_para_text(
                            payload, old_text, new_text, case_sensitive, use_regex
                        )
                        section_count += n
                        new_records[r_idx][2] = new_payload
                        if n > 0 and delta != 0:
                            # Translate the in-record edit position to paragraph-global
                            # and keep the earliest one across multiple PARA_TEXT records.
                            global_edit = group_text_base + edit_pos
                            if group_edit_pos == -1 or global_edit < group_edit_pos:
                                group_edit_pos = global_edit
                            group_delta += delta
                            # Patch the PARA_HEADER nChars for this group (delta only,
                            # so repeated edits in the same paragraph accumulate safely).
                            if header_idx >= 0:
                                h_payload = new_records[header_idx][2]
                                new_records[header_idx][2] = (
                                    self._patch_para_header_nchars(h_payload, delta)
                                )
                        # Advance the paragraph-global base by this record's ORIGINAL
                        # position count (CHAR_SHAPE/LINE_SEG positions reference the
                        # pre-edit coordinate space, which is what we shift against).
                        group_text_base += self._count_para_text_positions(payload)
                    elif tag_id == TAG_PARA_CHAR_SHAPE and group_delta != 0:
                        new_records[r_idx][2] = self._patch_char_shape_positions(
                            payload, group_edit_pos, group_delta
                        )
                    elif tag_id == TAG_PARA_LINE_SEG and group_delta != 0:
                        new_records[r_idx][2] = self._patch_line_seg_positions(
                            payload, group_edit_pos, group_delta
                        )

                if section_count > 0:
                    total_replaced += section_count

                    # Rebuild section binary
                    parts: list[bytes] = []
                    for tag_id, level, payload in new_records:
                        parts.append(self._build_record_header(tag_id, level, len(payload)))
                        parts.append(payload)
                    new_data = b"".join(parts)

                    # Re-encode the section to EXACTLY the original stream size.
                    # olefile.write_stream requires identical stream size, but naive
                    # zero-padding leaves garbage after the deflate stream
                    # (decompressobj.unused_data != original trailer), which Hancom flags
                    # as "문서가 손상되었거나 변조되었을 가능성". We instead pad with
                    # valid empty DEFLATE stored blocks and reproduce the original 8-byte
                    # trailer (crc32 + length), recomputed for the new content.
                    original_size = len(raw)
                    if compressed:
                        # Reproduce the trailer layout: if the original had a trailer,
                        # it is crc32(decompressed)+len(decompressed); recompute it.
                        if len(trailer) == 8:
                            new_trailer = struct.pack(
                                "<II", zlib.crc32(new_data) & 0xFFFFFFFF, len(new_data)
                            )
                        else:
                            new_trailer = trailer  # b"" for standard HWP (no trailer)

                        new_raw = self._build_section_stream(
                            new_data, original_size, new_trailer
                        )
                        if new_raw is None:
                            # Re-encoded section cannot fit within the original stream
                            # size. Growing an OLE stream is unsupported by olefile;
                            # the user must shorten the replacement or use HWPX.
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


# ─────────────────────────────────────────────────────────────────────────────
# HTML 렌더링 (표 보존) — 본문 흐름 그대로 <p>/<table> 혼합 HTML 생성
#
# extract_tables(표만 모음)·get_text_content(평문)와는 별개의 신규 기능.
# 편집/Diff 화면에서 HWP를 "표가 사라진 평문"이 아닌 실제 표 구조로 보여주기 위함.
# ─────────────────────────────────────────────────────────────────────────────

# HWP 5.0 레코드 태그 ID (HWPTAG_BEGIN = 16)
_TAG_PARA_TEXT = 67     # HWPTAG_PARA_TEXT
_TAG_LIST_HEADER = 72   # HWPTAG_LIST_HEADER (셀 경계)
_TAG_TABLE = 77         # HWPTAG_TABLE

# LIST_HEADER payload 내 셀 속성 바이트 오프셋 (실측 보정 완료).
#   payload = [nParas INT16][공통속성 UINT32][col U16][row U16][colSpan U16][rowSpan U16]...
#   즉 col=byte8, row=byte10, colSpan=byte12, rowSpan=byte14.
# 고시문 샘플의 nRows=12/nCols=9 표(셀96개), nRows=11/nCols=9 표 등 다수에서
# (row<nRows, col<nCols, span>=1) 범위를 모두 만족함을 검증함.
_CELL_COL_OFFSET = 8
_CELL_ROW_OFFSET = 10
_CELL_COLSPAN_OFFSET = 12
_CELL_ROWSPAN_OFFSET = 14

_TABLE_STYLE = 'border="1" style="border-collapse:collapse;width:100%"'


def _esc(text: str) -> str:
    """HTML escape (<, >, &, 따옴표)."""
    return html.escape(text, quote=True)


def _read_u16(payload: bytes, offset: int) -> int | None:
    """payload[offset:offset+2]를 UINT16(LE)로 읽는다. 범위 밖이면 None."""
    if offset + 2 <= len(payload):
        return struct.unpack_from("<H", payload, offset)[0]
    return None


def _decompress_sections(file_data: bytes) -> list[bytes]:
    """HWP 바이너리(OLE2)의 BodyText/SectionN 스트림들을 순서대로 디코딩한다."""
    svc = HwpService()
    svc._validate_ole_data(file_data)
    try:
        ole = olefile.OleFileIO(io.BytesIO(file_data))
    except Exception as e:  # pragma: no cover - 방어적
        raise HwpParseError(f"HWP 파일 열기 실패: {e}")

    sections: list[bytes] = []
    try:
        compressed = HwpService._is_hwp_compressed(file_data)
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
                    sections.append(zlib.decompress(raw, -15))
                except zlib.error as e:
                    raise HwpParseError(f"HWP 섹션 압축 해제 실패: {e}")
            else:
                sections.append(raw)
    finally:
        ole.close()
    return sections


def _iter_records(data: bytes):
    """섹션 바이너리를 (tag_id, level, payload) 레코드 시퀀스로 순회한다."""
    pos = 0
    n = len(data)
    while pos < n:
        if pos + 4 > n:
            break
        tag_data = struct.unpack_from("<I", data, pos)[0]
        tag_id = tag_data & 0x3FF
        level = (tag_data >> 10) & 0x3FF
        size = (tag_data >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            if pos + 4 > n:
                break
            size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        yield tag_id, level, data[pos : pos + size]
        pos += size


def _render_table_html(
    n_rows: int,
    n_cols: int,
    cells: list[dict],
) -> tuple[str, bool]:
    """셀 목록을 <table> HTML로 렌더한다.

    cells 각 항목: {"col","row","cspan","rspan","text"} (+선택적 "changed": bool)
    반환: (html, used_fallback)
      - 병합 정보(col/row/span)가 유효하면 그리드를 정확히 재구성하고
        병합 흡수 칸은 건너뛴다.
      - 정보가 신뢰할 수 없으면(범위 초과 등) nCols 단순분할 폴백.
    각 셀의 "changed"가 True면 <td>에 class="hwp-changed"를 부여한다.
    """
    def _td(cell: dict, attrs: str) -> str:
        cls = ' class="hwp-changed"' if cell.get("changed") else ""
        return f"<td{cls}{attrs}>{_esc(cell['text'])}</td>"

    # 병합 정보 유효성 검사: 모든 셀이 (row<nRows, col<nCols, span>=1)을 만족해야 함
    grid_ok = (
        n_rows > 0
        and n_cols > 0
        and bool(cells)
        and all(
            0 <= c["row"] < n_rows
            and 0 <= c["col"] < n_cols
            and c["cspan"] >= 1
            and c["rspan"] >= 1
            and c["row"] + c["rspan"] <= n_rows
            and c["col"] + c["cspan"] <= n_cols
            for c in cells
        )
    )

    if grid_ok:
        occupied = [[False] * n_cols for _ in range(n_rows)]
        # (row, col) → 셀 매핑
        cell_at: dict[tuple[int, int], dict] = {
            (c["row"], c["col"]): c for c in cells
        }
        # 병합 흡수 칸 표시
        for c in cells:
            for rr in range(c["row"], c["row"] + c["rspan"]):
                for cc in range(c["col"], c["col"] + c["cspan"]):
                    occupied[rr][cc] = True

        rows_html: list[str] = []
        for r in range(n_rows):
            tds: list[str] = []
            c_idx = 0
            while c_idx < n_cols:
                cell = cell_at.get((r, c_idx))
                if cell is not None:
                    attrs = ""
                    if cell["cspan"] > 1:
                        attrs += f' colspan="{cell["cspan"]}"'
                    if cell["rspan"] > 1:
                        attrs += f' rowspan="{cell["rspan"]}"'
                    tds.append(_td(cell, attrs))
                    c_idx += cell["cspan"]
                else:
                    # 위/왼쪽 병합에 흡수된 칸은 건너뜀
                    c_idx += 1
            if tds:
                rows_html.append("<tr>" + "".join(tds) + "</tr>")
        return f"<table {_TABLE_STYLE}>{''.join(rows_html)}</table>", False

    # ── 폴백: nCols 단순분할 (등장 순서대로 셀을 행으로 묶음) ──
    rows_html = []
    col_count = n_cols if n_cols > 0 else 1
    for r_start in range(0, len(cells), col_count):
        row = cells[r_start : r_start + col_count]
        tds = "".join(_td(c, "") for c in row)
        rows_html.append("<tr>" + tds + "</tr>")
    # 폴백 사용을 HTML 주석으로 표시
    comment = "<!-- table fallback: merge-cell parse uncertain, simple nCols split -->"
    return f"{comment}<table {_TABLE_STYLE}>{''.join(rows_html)}</table>", True


def _extract_section_blocks(data: bytes) -> list[dict]:
    """단일 HWP 섹션을 본문 순서대로 '블록 구조' 리스트로 추출한다.

    블록은 두 종류:
      문단: {"type": "para", "text": str}
      표  : {"type": "table", "n_rows": int, "n_cols": int,
             "cells": [{"col","row","cspan","rspan","text"}, ...]}
    표 안에 속한 PARA_TEXT는 별도 문단으로 내보내지 않고 셀 텍스트로 흡수된다.
    HTML 직렬화/비교가 이 구조를 공유한다.
    """
    records = list(_iter_records(data))
    blocks: list[dict] = []

    i = 0
    n = len(records)
    while i < n:
        tag_id, level, payload = records[i]

        if tag_id == _TAG_TABLE:
            # 표 메타: [4 attr][2 nRows][2 nCols]
            if len(payload) >= 8:
                n_rows = struct.unpack_from("<H", payload, 4)[0]
                n_cols = struct.unpack_from("<H", payload, 6)[0]
            else:
                n_rows, n_cols = 0, 0
            table_level = level

            cells: list[dict] = []
            cur: dict | None = None
            j = i + 1
            while j < n:
                t_id, t_lv, t_pl = records[j]
                if t_lv < table_level:
                    break
                if t_id == _TAG_TABLE and t_lv == table_level:
                    break
                if t_id == _TAG_LIST_HEADER and t_lv == table_level:
                    col = _read_u16(t_pl, _CELL_COL_OFFSET)
                    row = _read_u16(t_pl, _CELL_ROW_OFFSET)
                    cspan = _read_u16(t_pl, _CELL_COLSPAN_OFFSET)
                    rspan = _read_u16(t_pl, _CELL_ROWSPAN_OFFSET)
                    cur = {
                        "col": col if col is not None else 0,
                        "row": row if row is not None else 0,
                        "cspan": cspan if cspan and cspan >= 1 else 1,
                        "rspan": rspan if rspan and rspan >= 1 else 1,
                        "text": "",
                    }
                    cells.append(cur)
                elif t_id == _TAG_PARA_TEXT and t_lv > table_level and cur is not None:
                    para = HwpService._parse_hwp_para_text(t_pl).strip()
                    if para:
                        cur["text"] = (cur["text"] + " " + para).strip() if cur["text"] else para
                j += 1

            if cells:
                blocks.append({
                    "type": "table",
                    "n_rows": n_rows,
                    "n_cols": n_cols,
                    "cells": cells,
                })
            i = j
            continue

        if tag_id == _TAG_PARA_TEXT:
            # 표 밖 일반 문단 (표 안 문단은 위 TABLE 분기에서 흡수됨)
            para = HwpService._parse_hwp_para_text(payload).strip()
            if para:
                blocks.append({"type": "para", "text": para})

        i += 1

    return blocks


def _serialize_block(block: dict) -> str:
    """단일 블록 구조를 HTML 조각으로 직렬화한다.

    block에 비교 마킹이 들어 있으면 그대로 반영한다:
      - 문단: block["html"]가 있으면(단어 단위 diff 결과) 그것을 본문으로 사용,
        없으면 escape된 평문.
      - 표  : 각 셀의 "changed" 플래그가 <td class="hwp-changed">로 반영됨.
    """
    if block["type"] == "table":
        html_frag, _used_fallback = _render_table_html(
            block["n_rows"], block["n_cols"], block["cells"]
        )
        return html_frag
    # para
    inner = block.get("html")
    if inner is None:
        inner = _esc(block["text"])
    return f"<p>{inner}</p>"


def _render_section_html(data: bytes) -> tuple[list[str], int, int, int]:
    """단일 섹션을 본문 순서대로 HTML 블록 리스트로 변환한다.

    반환: (blocks, table_count, para_count, fallback_count)
    표 안에 속한 PARA_TEXT는 별도 <p>로 내보내지 않고 셀 텍스트로 흡수된다.
    """
    structured = _extract_section_blocks(data)
    blocks: list[str] = []
    table_count = 0
    para_count = 0
    fallback_count = 0

    for block in structured:
        if block["type"] == "table":
            table_html, used_fallback = _render_table_html(
                block["n_rows"], block["n_cols"], block["cells"]
            )
            blocks.append(table_html)
            table_count += 1
            if used_fallback:
                fallback_count += 1
        else:
            blocks.append(f"<p>{_esc(block['text'])}</p>")
            para_count += 1

    return blocks, table_count, para_count, fallback_count


def _hwpx_cell_text(tc: ET.Element) -> str:
    return "".join(
        t_el.text or ""
        for t_el in tc.iter()
        if _get_local_name(t_el.tag) == "t"
    ).strip()


def _extract_hwpx_blocks(file_data: bytes) -> list[dict]:
    """HWPX(ZIP+XML)를 본문 순서대로 '블록 구조' 리스트로 추출한다.

    HWP 바이너리와 동일한 블록 구조를 사용한다:
      문단: {"type": "para", "text": str}
      표  : {"type": "table", "rows": [[{"text","colspan","rowspan"}, ...], ...]}
            (HWPX는 행 단위 tr/tc 구조이므로 행 그리드 형태로 보존)
    표가 하나도 없으면 평문 문단 폴백.
    """
    svc = HwpService()
    svc._validate_zip_data(file_data)
    blocks: list[dict] = []
    has_table = False

    try:
        with zipfile.ZipFile(io.BytesIO(file_data), "r") as zf:
            for section_file in svc._get_section_files(zf):
                root = SafeET.fromstring(zf.read(section_file))
                for el in root.iter():
                    name = _get_local_name(el.tag)
                    if name == "tbl":
                        rows: list[list[dict]] = []
                        for tr in el:
                            if _get_local_name(tr.tag) != "tr":
                                continue
                            row_cells: list[dict] = []
                            for tc in tr:
                                if _get_local_name(tc.tag) != "tc":
                                    continue
                                colspan = 1
                                rowspan = 1
                                for span in tc.iter():
                                    if _get_local_name(span.tag) == "cellSpan":
                                        cs = span.get("colSpan")
                                        rs = span.get("rowSpan")
                                        if cs and cs.isdigit() and int(cs) > 1:
                                            colspan = int(cs)
                                        if rs and rs.isdigit() and int(rs) > 1:
                                            rowspan = int(rs)
                                        break
                                row_cells.append({
                                    "text": _hwpx_cell_text(tc),
                                    "colspan": colspan,
                                    "rowspan": rowspan,
                                })
                            if row_cells:
                                rows.append(row_cells)
                        if rows:
                            blocks.append({"type": "table", "rows": rows})
                            has_table = True
    except (zipfile.BadZipFile, ET.ParseError) as e:
        raise HwpParseError(f"HWPX HTML 렌더링 실패: {e}")

    if not has_table:
        text = svc._extract_text_from_bytes(file_data)
        blocks = [
            {"type": "para", "text": line.strip()}
            for line in text.split("\n")
            if line.strip()
        ]

    return blocks


def _serialize_hwpx_table(block: dict) -> str:
    """HWPX 표 블록(행 그리드)을 <table> HTML로 직렬화한다.

    각 셀의 "changed" 플래그가 <td class="hwp-changed">로 반영된다.
    """
    rows_html: list[str] = []
    for row in block["rows"]:
        tds: list[str] = []
        for cell in row:
            attrs = ""
            if cell.get("colspan", 1) > 1:
                attrs += f' colspan="{cell["colspan"]}"'
            if cell.get("rowspan", 1) > 1:
                attrs += f' rowspan="{cell["rowspan"]}"'
            cls = ' class="hwp-changed"' if cell.get("changed") else ""
            tds.append(f"<td{cls}{attrs}>{_esc(cell['text'])}</td>")
        if tds:
            rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table {_TABLE_STYLE}>{''.join(rows_html)}</table>"


def _serialize_hwpx_block(block: dict) -> str:
    """단일 HWPX 블록 구조를 HTML 조각으로 직렬화한다."""
    if block["type"] == "table":
        return _serialize_hwpx_table(block)
    inner = block.get("html")
    if inner is None:
        inner = _esc(block["text"])
    return f"<p>{inner}</p>"


def _render_hwpx_to_html(file_data: bytes) -> str:
    """HWPX(ZIP+XML)를 본문 순서대로 <p>/<table> HTML로 변환한다."""
    blocks = _extract_hwpx_blocks(file_data)
    return "\n".join(_serialize_hwpx_block(b) for b in blocks)


def render_hwp_to_html(file_data: bytes, file_type: str) -> str:
    """HWP 바이너리/HWPX를 표 보존 HTML 조각으로 렌더한다.

    본문 흐름 그대로 문단(<p>)과 표(<table>)가 등장 순서로 섞인 HTML을 반환한다.
    extract_tables(표만)·get_text_content(평문)와는 별개의 신규 함수.

    Args:
        file_data: 파일 바이트.
        file_type: "hwp"(OLE2 바이너리) 또는 "hwpx"(ZIP+XML).

    Returns:
        <p>/<table> 혼합 HTML 문자열 (escape 처리 완료).
    """
    if not file_data:
        raise HwpParseError("빈 파일 데이터입니다.")

    if file_type == "hwp":
        sections = _decompress_sections(file_data)
        all_blocks: list[str] = []
        for sec in sections:
            blocks, _t, _p, _f = _render_section_html(sec)
            all_blocks.extend(blocks)
        return "\n".join(all_blocks)

    return _render_hwpx_to_html(file_data)


# ─────────────────────────────────────────────────────────────────────────────
# 원본/수정본 비교 HTML (바뀐 셀/단어만 hwp-changed 클래스로 표시)
#
# 교체는 텍스트만 바꾸므로 원본·수정본의 블록 구조(문단 수, 표 수, 표의 행/열/셀
# 구조)는 동일하다고 가정 → 인덱스로 1:1 정렬해 비교한다.
# 구조가 어긋나면(길이 불일치 등) 안전 폴백으로 해당 블록을 클래스 없이 그대로
# 출력한다.
# ─────────────────────────────────────────────────────────────────────────────

# 단어 단위 토크나이저: 공백 묶음과 비공백 묶음을 토큰으로 분리(공백 보존).
_WORD_TOKEN_RE = re.compile(r"\s+|[^\s]+")

# 변경 강조에 쓰는 통일된 클래스명(원본/수정본 양쪽 동일).
_CHANGED_CLASS = "hwp-changed"


def _tokenize_words(text: str) -> list[str]:
    """문단 텍스트를 공백을 보존하는 토큰 리스트로 분할한다."""
    return _WORD_TOKEN_RE.findall(text)


def _word_diff_html(original: str, modified: str) -> tuple[str, str]:
    """두 문단 텍스트를 단어 단위로 비교해 변경 토큰만 강조한 HTML을 반환한다.

    반환: (original_html, modified_html)
      - original_html: 삭제/이전 토큰을 <span class="hwp-changed">로 감쌈.
      - modified_html: 추가/새 토큰을 <span class="hwp-changed">로 감쌈.
    텍스트는 모두 HTML escape 처리된다. 동일하면 강조 없이 평문.
    """
    a = _tokenize_words(original)
    b = _tokenize_words(modified)
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)

    orig_parts: list[str] = []
    mod_parts: list[str] = []

    def _wrap(tokens: list[str], changed: bool) -> str:
        joined = _esc("".join(tokens))
        if not changed or joined == "":
            return joined
        return f'<span class="{_CHANGED_CLASS}">{joined}</span>'

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            orig_parts.append(_wrap(a[i1:i2], False))
            mod_parts.append(_wrap(b[j1:j2], False))
        elif tag == "delete":
            orig_parts.append(_wrap(a[i1:i2], True))
        elif tag == "insert":
            mod_parts.append(_wrap(b[j1:j2], True))
        else:  # replace
            orig_parts.append(_wrap(a[i1:i2], True))
            mod_parts.append(_wrap(b[j1:j2], True))

    return "".join(orig_parts), "".join(mod_parts)


def _extract_file_blocks(file_data: bytes, file_type: str) -> list[dict]:
    """파일 전체(모든 섹션)를 블록 구조 리스트로 추출한다.

    hwp: 모든 BodyText 섹션의 블록을 순서대로 이어붙인다.
    hwpx: _extract_hwpx_blocks 결과.
    """
    if file_type == "hwp":
        sections = _decompress_sections(file_data)
        all_blocks: list[dict] = []
        for sec in sections:
            all_blocks.extend(_extract_section_blocks(sec))
        return all_blocks
    return _extract_hwpx_blocks(file_data)


def _mark_hwp_table_changes(orig: dict, mod: dict) -> None:
    """HWP 표 블록 한 쌍을 셀 인덱스로 비교해 changed 플래그를 설정한다.

    셀 목록 길이가 다르면(구조 불일치) 아무 셀도 마킹하지 않는다(안전 폴백).
    """
    o_cells = orig["cells"]
    m_cells = mod["cells"]
    if len(o_cells) != len(m_cells):
        return
    for oc, mc in zip(o_cells, m_cells):
        if oc["text"] != mc["text"]:
            oc["changed"] = True
            mc["changed"] = True


def _mark_hwpx_table_changes(orig: dict, mod: dict) -> None:
    """HWPX 표 블록 한 쌍을 행/셀 인덱스로 비교해 changed 플래그를 설정한다.

    행 수 또는 어느 행의 셀 수가 다르면 그 행은 마킹하지 않는다(안전 폴백).
    """
    o_rows = orig["rows"]
    m_rows = mod["rows"]
    if len(o_rows) != len(m_rows):
        return
    for o_row, m_row in zip(o_rows, m_rows):
        if len(o_row) != len(m_row):
            continue
        for oc, mc in zip(o_row, m_row):
            if oc["text"] != mc["text"]:
                oc["changed"] = True
                mc["changed"] = True


def render_hwp_compare_html(
    original_data: bytes, modified_data: bytes, file_type: str
) -> dict:
    """원본·수정본을 셀/단어 단위로 비교해 바뀐 부분을 강조한 HTML 쌍을 만든다.

    반환: {"original_html": str, "modified_html": str}
      - 표 셀: 같은 위치 셀 텍스트가 다르면 <td class="hwp-changed">.
      - 문단 : 같은 위치 문단 텍스트가 다르면 단어 단위 diff로 바뀐 토큰만
               <span class="hwp-changed">로 감쌈.
    구조가 어긋나면(블록 종류/개수/표 구조 불일치) 해당 블록은 클래스 없이
    그대로 출력(안전 폴백). 클래스명은 양쪽 모두 'hwp-changed'로 통일.

    Args:
        original_data: 원본 파일 바이트.
        modified_data: 수정본 파일 바이트.
        file_type: "hwp" 또는 "hwpx".
    """
    if not original_data or not modified_data:
        raise HwpParseError("빈 파일 데이터입니다.")

    orig_blocks = _extract_file_blocks(original_data, file_type)
    mod_blocks = _extract_file_blocks(modified_data, file_type)

    serialize = _serialize_block if file_type == "hwp" else _serialize_hwpx_block

    # 블록 개수가 다르면 비교를 포기하고 각자 그대로 렌더(안전 폴백).
    if len(orig_blocks) != len(mod_blocks):
        return {
            "original_html": "\n".join(serialize(b) for b in orig_blocks),
            "modified_html": "\n".join(serialize(b) for b in mod_blocks),
        }

    for orig, mod in zip(orig_blocks, mod_blocks):
        if orig["type"] != mod["type"]:
            continue  # 종류 불일치 → 폴백(마킹 없음)

        if orig["type"] == "para":
            if orig["text"] != mod["text"]:
                o_html, m_html = _word_diff_html(orig["text"], mod["text"])
                orig["html"] = o_html
                mod["html"] = m_html
        elif orig["type"] == "table":
            if file_type == "hwp":
                _mark_hwp_table_changes(orig, mod)
            else:
                _mark_hwpx_table_changes(orig, mod)

    return {
        "original_html": "\n".join(serialize(b) for b in orig_blocks),
        "modified_html": "\n".join(serialize(b) for b in mod_blocks),
    }
