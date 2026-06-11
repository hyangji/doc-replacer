"""테스트용 HWP 바이너리/HWPX 픽스처 생성기.

저장소에 실제 HWP 샘플이 없으므로 테스트가 자급자족하도록 최소한의 유효한
HWP(OLE2/CFB) 및 HWPX(ZIP) 파일을 직접 만든다.

HWP 바이너리는:
  - 압축(zlib raw-deflate) 섹션 사용(_build_section_stream 경로 검증을 위해).
  - FileHeader(props bit0=1 = 압축), DocInfo(빈 스트림), BodyText/Section0 스트림.
  - Section0 레코드 = 표 1개(2x2 셀) + 표 밖 문단 2개.
HWPX 는 한컴 네임스페이스를 쓰는 최소 섹션 XML(표 + 문단).
"""

import io
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

# ── HWP 5.0 레코드 태그 ──
TAG_DOCUMENT_PROPERTIES = 16
TAG_PARA_HEADER = 66
TAG_PARA_TEXT = 67
TAG_PARA_CHAR_SHAPE = 68
TAG_PARA_LINE_SEG = 69
TAG_LIST_HEADER = 72
TAG_TABLE = 77

# LIST_HEADER 셀 속성 오프셋(hwp_service 와 동일)
_CELL_COL_OFFSET = 8
_CELL_ROW_OFFSET = 10
_CELL_COLSPAN_OFFSET = 12
_CELL_ROWSPAN_OFFSET = 14


def _rec_header(tag_id: int, level: int, size: int) -> bytes:
    if size >= 0xFFF:
        tag_data = tag_id | (level << 10) | (0xFFF << 20)
        return struct.pack("<II", tag_data, size)
    tag_data = tag_id | (level << 10) | (size << 20)
    return struct.pack("<I", tag_data)


def _record(tag_id: int, level: int, payload: bytes) -> bytes:
    return _rec_header(tag_id, level, len(payload)) + payload


def _para_text_payload(text: str) -> bytes:
    """printable WCHAR 만으로 구성된 PARA_TEXT payload(UTF-16LE)."""
    return text.encode("utf-16-le")


def _para_header_payload(nchars: int) -> bytes:
    """nChars(저비트 31)만 의미있게 채운 최소 PARA_HEADER payload."""
    # u32[0] = nChars (top bit flag = 0). 나머지는 0으로 채워도 파싱엔 무방.
    return struct.pack("<I", nchars & 0x7FFFFFFF) + b"\x00" * 18


def _char_shape_payload() -> bytes:
    """단일 엔트리 (charPos=0, charShapeId=0)."""
    return struct.pack("<II", 0, 0)


def _line_seg_payload() -> bytes:
    """단일 세그먼트(36바이트), 첫 i32 textpos=0."""
    return struct.pack("<i", 0) + b"\x00" * 32


def _para_group(level: int, text: str) -> bytes:
    """PARA_HEADER + PARA_TEXT + CHAR_SHAPE + LINE_SEG 한 문단 그룹."""
    nchars = len(text)
    return (
        _record(TAG_PARA_HEADER, level, _para_header_payload(nchars))
        + _record(TAG_PARA_TEXT, level, _para_text_payload(text))
        + _record(TAG_PARA_CHAR_SHAPE, level, _char_shape_payload())
        + _record(TAG_PARA_LINE_SEG, level, _line_seg_payload())
    )


def _list_header_payload(col: int, row: int, cspan: int = 1, rspan: int = 1) -> bytes:
    pl = bytearray(16)
    struct.pack_into("<H", pl, _CELL_COL_OFFSET, col)
    struct.pack_into("<H", pl, _CELL_ROW_OFFSET, row)
    struct.pack_into("<H", pl, _CELL_COLSPAN_OFFSET, cspan)
    struct.pack_into("<H", pl, _CELL_ROWSPAN_OFFSET, rspan)
    return bytes(pl)


def build_section_records(
    table_cells: list[tuple[int, int, str]],
    n_rows: int,
    n_cols: int,
    paras: list[str],
) -> bytes:
    """표 1개(셀=table_cells) + 표 밖 문단(paras)으로 섹션 바이너리를 구성한다.

    table_cells 각 항목: (col, row, text)
    """
    parts: list[bytes] = []

    # 표 밖 선행 문단(있으면) — 표보다 앞에 둔다.
    # 단순화를 위해 paras 의 절반은 표 앞, 절반은 표 뒤로 배치한다.
    pre = paras[: len(paras) // 2]
    post = paras[len(paras) // 2 :]

    for t in pre:
        parts.append(_para_group(0, t))

    # 표: TABLE(level 1) → 각 셀 LIST_HEADER(level 1) + 내부 문단(level 2)
    table_level = 1
    tbl_payload = bytearray(8)
    struct.pack_into("<H", tbl_payload, 4, n_rows)
    struct.pack_into("<H", tbl_payload, 6, n_cols)
    parts.append(_record(TAG_TABLE, table_level, bytes(tbl_payload)))

    for (col, row, text) in table_cells:
        parts.append(
            _record(
                TAG_LIST_HEADER,
                table_level,
                _list_header_payload(col, row),
            )
        )
        parts.append(_para_group(table_level + 1, text))

    for t in post:
        parts.append(_para_group(0, t))

    return b"".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 최소 CFB(OLE2) Writer
#
# 모든 스트림을 512바이트 섹터 FAT 에 넣기 위해 각 스트림을 >= 4096 바이트로
# 패딩한다(미니FAT 회피). FileHeader 만 정확히 256바이트가 필요하므로 예외적으로
# 미니스트림에 넣지 않도록 4096 으로 패딩하지 않고… → 단순화를 위해 FileHeader
# 도 512의 배수로 패딩하고 regular FAT 에 넣는다(olefile 은 헤더 앞 256바이트만
# 읽으므로 뒤 패딩 무방).
# ─────────────────────────────────────────────────────────────────────────────

SECTOR = 512
ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF
FATSECT = 0xFFFFFFFD


def _file_header_stream(compressed: bool) -> bytes:
    """HWP FileHeader 스트림(256바이트). 시그니처 + 버전 + 속성플래그."""
    data = bytearray(256)
    sig = "HWP Document File".encode("ascii")
    data[0 : len(sig)] = sig
    # 32바이트 시그니처 영역 이후 버전(4바이트) — 5.0.0.0
    struct.pack_into("<I", data, 32, 0x05000000)
    # 속성 플래그(offset 36): bit0 = 압축 여부
    struct.pack_into("<I", data, 36, 1 if compressed else 0)
    return bytes(data)


def _pad_sector(data: bytes) -> bytes:
    if len(data) % SECTOR != 0:
        data = data + b"\x00" * (SECTOR - (len(data) % SECTOR))
    return data


def build_hwp_bytes(
    table_cells: list[tuple[int, int, str]],
    n_rows: int,
    n_cols: int,
    paras: list[str],
    compressed: bool = True,
) -> bytes:
    """표 + 문단을 담은 최소 유효 HWP(OLE2) 바이트를 만든다.

    compressed=True 일 때 원본 섹션 스트림을 '여유(slack)가 있는 유효 deflate'로
    만든다(빈 stored 블록 패딩). 이렇게 해야:
      1) 선언 size(=deflate 길이) >= 4096 → olefile 이 regular FAT 스트림으로 인식.
      2) 편집으로 텍스트가 늘어나도 minimal-deflate(new) <= target_size 라서
         _build_section_stream 으로 무손실 재저장 가능(실제 HWP 의 슬랙을 모사).
    스트림 끝에 trailer 가 없도록(unused_data == b"") 모든 패딩을 유효 deflate 로 둔다.
    """
    section_raw = build_section_records(table_cells, n_rows, n_cols, paras)
    if compressed:
        from app.services.hwp_service import HwpService

        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        minimal = co.compress(section_raw) + co.flush()
        # 4096 이상 + 충분한 슬랙(편집 성장분 흡수). 5의 배수 여유는
        # _build_section_stream 내부 빈 블록(5바이트) 패딩이 맞춰준다.
        target = max(4096, len(minimal) + 1024)
        section_stream = HwpService._build_section_stream(section_raw, target, b"")
        if section_stream is None:  # pragma: no cover - 방어적
            raise RuntimeError("픽스처 섹션 스트림 생성 실패")
    else:
        section_stream = section_raw

    fileheader = _file_header_stream(compressed)
    docinfo = b"\x00" * 16  # 빈 DocInfo(파싱에 영향 없음)

    # 스트림 목록: 이름 → 데이터
    # 디렉토리 구조: Root → [FileHeader, DocInfo, BodyText → Section0]
    streams = {
        "FileHeader": fileheader,
        "DocInfo": docinfo,
        "Section0": section_stream,
    }

    return _assemble_cfb(streams)


def _assemble_cfb(streams: dict[str, bytes]) -> bytes:
    """주어진 스트림들로 CFB(OLE2) 파일을 조립한다.

    디렉토리 트리(고정):
        Root Entry
          ├─ FileHeader
          ├─ DocInfo
          └─ BodyText (storage)
               └─ Section0
    모든 스트림은 regular FAT(512 섹터)에 저장(미니FAT 미사용)하기 위해 최소
    4096바이트로 패딩한다. olefile 은 스트림 size 필드를 신뢰하므로 실제 데이터
    길이를 정확히 기록한다.
    """
    # 각 스트림을 섹터 패딩
    fh = streams["FileHeader"]
    di = streams["DocInfo"]
    sec0 = streams["Section0"]

    # regular FAT 사용 강제: 4096 미만이면 4096으로 패딩
    def _force_regular(data: bytes) -> bytes:
        if len(data) < 4096:
            data = data + b"\x00" * (4096 - len(data))
        return _pad_sector(data)

    fh_p = _force_regular(fh)
    di_p = _force_regular(di)
    # Section0 은 deflate 데이터 무결성이 중요(트레일링 0 패딩이 trailer 로 잡혀
    # _build_section_stream 을 깨뜨림). 따라서 선언 size = 실제 deflate 길이로 두고,
    # regular FAT 인식을 위해 deflate 길이 자체가 >=4096 이어야 한다(호출부 보장).
    sec0_p = _pad_sector(sec0)

    # 섹터 배치(데이터 영역). 각 스트림은 연속 섹터 체인.
    # 섹터 인덱스 0부터: FileHeader, DocInfo, Section0, 그 다음 디렉토리.
    payload_chunks = [fh_p, di_p, sec0_p]
    # 선언 size: FileHeader/DocInfo 는 패딩 길이(>=4096, 파싱에 무해한 0 패딩),
    # Section0 은 실제 deflate 길이(트레일링 0 없이 정확히).
    stream_sizes = [len(fh_p), len(di_p), len(sec0)]

    # 디렉토리 엔트리(128바이트씩). 5개: Root, FileHeader, DocInfo, BodyText, Section0
    dir_entries = _build_dir_entries(stream_sizes, payload_chunks)
    dir_stream = b"".join(dir_entries)
    dir_p = _pad_sector(dir_stream)

    # 전체 섹터 배치: [streams..., directory]
    all_chunks = payload_chunks + [dir_p]

    # 각 청크의 시작 섹터/섹터 수 계산
    sector_layout = []  # (start_sector, n_sectors)
    cur = 0
    for chunk in all_chunks:
        n = len(chunk) // SECTOR
        sector_layout.append((cur, n))
        cur += n
    total_data_sectors = cur

    # FAT 구성: 각 청크는 연속 체인, 마지막 섹터는 ENDOFCHAIN.
    fat = [FREESECT] * total_data_sectors
    for (start, n) in sector_layout:
        for k in range(n):
            if k == n - 1:
                fat[start + k] = ENDOFCHAIN
            else:
                fat[start + k] = start + k + 1

    # FAT 자체를 담을 섹터 수 계산(각 FAT 섹터 = 128 엔트리)
    # FAT 섹터도 total 에 포함되어 FAT 안에서 FATSECT 로 표시된다.
    entries_per_fat = SECTOR // 4
    # 반복 계산: FAT 섹터 추가 → total 증가 → 다시 FAT 섹터 수 계산
    n_fat_sectors = 1
    while True:
        total_with_fat = total_data_sectors + n_fat_sectors
        needed = (total_with_fat + entries_per_fat - 1) // entries_per_fat
        if needed <= n_fat_sectors:
            break
        n_fat_sectors = needed

    total_sectors = total_data_sectors + n_fat_sectors
    fat = fat + [FREESECT] * (total_sectors - len(fat))
    # FAT 섹터 위치 = 데이터 섹터 뒤
    fat_sector_start = total_data_sectors
    for k in range(n_fat_sectors):
        fat[fat_sector_start + k] = FATSECT

    # FAT 스트림 직렬화(섹터 패딩)
    fat_bytes = b"".join(struct.pack("<I", x) for x in fat)
    fat_bytes = _pad_sector(fat_bytes)

    # 디렉토리 시작 섹터 = sector_layout 의 마지막(디렉토리) start
    dir_start_sector = sector_layout[-1][0]

    # CFB 헤더(512바이트)
    header = bytearray(SECTOR)
    header[0:8] = bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])
    # CLSID 16바이트 0
    struct.pack_into("<H", header, 24, 0x003E)  # minor version
    struct.pack_into("<H", header, 26, 0x0003)  # major version 3 (512 섹터)
    struct.pack_into("<H", header, 28, 0xFFFE)  # byte order
    struct.pack_into("<H", header, 30, 9)       # sector shift = 2^9 = 512
    struct.pack_into("<H", header, 32, 6)       # mini sector shift = 2^6 = 64
    struct.pack_into("<I", header, 44, n_fat_sectors)  # number of FAT sectors
    struct.pack_into("<I", header, 48, dir_start_sector)  # first dir sector
    struct.pack_into("<I", header, 56, 0x00001000)  # mini stream cutoff = 4096
    struct.pack_into("<I", header, 60, ENDOFCHAIN)  # first mini FAT sector
    struct.pack_into("<I", header, 64, 0)           # number of mini FAT sectors
    struct.pack_into("<I", header, 68, ENDOFCHAIN)  # first DIFAT sector
    struct.pack_into("<I", header, 72, 0)           # number of DIFAT sectors
    # DIFAT(첫 109개) — FAT 섹터 위치
    difat_off = 76
    for k in range(109):
        if k < n_fat_sectors:
            struct.pack_into("<I", header, difat_off + k * 4, fat_sector_start + k)
        else:
            struct.pack_into("<I", header, difat_off + k * 4, FREESECT)

    body = b"".join(all_chunks) + fat_bytes
    return bytes(header) + body


def _dir_entry(
    name: str,
    obj_type: int,
    left: int,
    right: int,
    child: int,
    start_sector: int,
    size: int,
) -> bytes:
    """128바이트 디렉토리 엔트리."""
    entry = bytearray(128)
    name_utf16 = name.encode("utf-16-le")
    entry[0 : len(name_utf16)] = name_utf16
    name_len = len(name_utf16) + 2  # null 종료 포함
    struct.pack_into("<H", entry, 64, name_len)
    entry[66] = obj_type  # 1=storage, 2=stream, 5=root
    entry[67] = 1          # color = black
    struct.pack_into("<i", entry, 68, left)
    struct.pack_into("<i", entry, 72, right)
    struct.pack_into("<i", entry, 76, child)
    # CLSID(80~95) 0
    struct.pack_into("<I", entry, 116, start_sector)
    struct.pack_into("<Q", entry, 120, size)
    return bytes(entry)


def _build_dir_entries(
    stream_sizes: list[int], payload_chunks: list[bytes]
) -> list[bytes]:
    """디렉토리 엔트리 5개를 만든다.

    인덱스: 0=Root, 1=FileHeader, 2=DocInfo, 3=BodyText(storage), 4=Section0
    섹터 배치: payload_chunks = [FileHeader, DocInfo, Section0] (start 0,1,2... )
    """
    fh_size, di_size, sec0_size = stream_sizes
    # payload_chunks 의 시작 섹터(섹터 단위)
    fh_start = 0
    di_start = len(payload_chunks[0]) // SECTOR
    sec0_start = di_start + len(payload_chunks[1]) // SECTOR

    NOSTREAM = -1
    # Root: child = 디렉토리 트리 루트의 자식(여기선 FileHeader=1을 루트로 한 작은 트리)
    # 단순 트리: Root.child → BodyText(3)을 루트로? olefile 은 red-black 트리를
    # 엄격히 검증하지 않고 left/right/child 를 따라 순회한다. 안전한 균형을 위해
    # 이름 길이 기준 정렬 트리를 구성한다.
    #
    # 자식들(FileHeader, DocInfo, BodyText)을 Root 의 자식 트리로 둔다.
    # 정렬 키: (len(name), name upper). 이름들: BodyText(8), DocInfo(7), FileHeader(10)
    #   → 길이 순: DocInfo(7) < BodyText(8) < FileHeader(10)
    # 트리: 중앙 BodyText(3) 를 root, left=DocInfo(2), right=FileHeader(1)
    entries = []
    # 0 Root
    entries.append(
        _dir_entry("Root Entry", 5, NOSTREAM, NOSTREAM, 3, 0, 0)
    )
    # 1 FileHeader (stream)
    entries.append(
        _dir_entry("FileHeader", 2, NOSTREAM, NOSTREAM, NOSTREAM, fh_start, fh_size)
    )
    # 2 DocInfo (stream)
    entries.append(
        _dir_entry("DocInfo", 2, NOSTREAM, NOSTREAM, NOSTREAM, di_start, di_size)
    )
    # 3 BodyText (storage) — Root 자식 트리의 루트, child → Section0(4)
    entries.append(
        _dir_entry("BodyText", 1, 2, 1, 4, 0, 0)
    )
    # 4 Section0 (stream) — BodyText 의 유일 자식
    entries.append(
        _dir_entry("Section0", 2, NOSTREAM, NOSTREAM, NOSTREAM, sec0_start, sec0_size)
    )
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# HWPX 픽스처
# ─────────────────────────────────────────────────────────────────────────────

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _hwpx_para(parent: ET.Element, text: str) -> None:
    p = ET.SubElement(parent, f"{{{_HP}}}p")
    run = ET.SubElement(p, f"{{{_HP}}}run")
    t = ET.SubElement(run, f"{{{_HP}}}t")
    t.text = text


def build_hwpx_bytes(
    table_rows: list[list[str]] | None = None,
    paras: list[str] | None = None,
) -> bytes:
    """표(table_rows) + 문단(paras)을 담은 최소 HWPX 바이트.

    주의: _extract_hwpx_blocks 는 표가 하나라도 있으면 표만 블록으로 만든다.
    따라서 표가 있는 픽스처에서 paras 는 eid 를 받지 못한다(렌더 규칙과 동일).
    """
    root = ET.Element(f"{{{_HS}}}sec")

    if table_rows is not None:
        tbl = ET.SubElement(root, f"{{{_HP}}}tbl")
        for row in table_rows:
            tr = ET.SubElement(tbl, f"{{{_HP}}}tr")
            for cell_text in row:
                tc = ET.SubElement(tr, f"{{{_HP}}}tc")
                # subList → p → run → t (셀 텍스트)
                sublist = ET.SubElement(tc, f"{{{_HP}}}subList")
                _hwpx_para(sublist, cell_text)

    if paras:
        for t in paras:
            _hwpx_para(root, t)

    xml = ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", xml)
        zf.writestr("META-INF/container.xml", "<container/>")
    buf.seek(0)
    return buf.read()
