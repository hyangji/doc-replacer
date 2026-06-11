"""구조 보존 인라인 텍스트 편집(A안) 테스트.

editable 렌더의 data-eid 부여 규칙과 apply_block_edits 의 위치 기반 텍스트 교체를
HWP(바이너리)·HWPX 양쪽에서 검증한다. 검증 포인트:
  1. data-eid 가 0..N-1 연속이고 apply 순회 eid 와 매핑이 일치.
  2. 한 셀만 edit → 다른 셀/문단 불변, 표 구조(행/열/셀수) 불변, 재파싱 가능.
  3. 동일 텍스트 셀 2개 중 하나만 edit → 다른 쪽 불변(중복 오염 없음).
  4. HWP: 길이 증가도 정상 저장, 너무 길면 HwpParseError.
"""

import asyncio
import io
import re
import zipfile
from xml.etree import ElementTree as ET

import olefile
import pytest

from app.services.hwp_service import (
    HwpParseError,
    HwpService,
    apply_block_edits,
    render_hwp_compare_html,
    render_hwp_to_html,
)
from tests.hwp_fixtures import build_hwp_bytes, build_hwpx_bytes

svc = HwpService()


# ── 공용 헬퍼 ──


def _eid_text_map(html: str) -> dict[int, str]:
    """편집용 HTML 에서 {eid: 셀/문단 텍스트} 매핑을 추출한다."""
    out: dict[int, str] = {}
    for m in re.finditer(r'data-eid="(\d+)"[^>]*>([^<]*)<', html):
        out[int(m.group(1))] = m.group(2)
    return out


def _hwp_fixture() -> bytes:
    # 2x2 표(셀 4개) + 표 밖 문단 2개. (0,0)/(0,1) 셀 텍스트가 'dup' 로 중복.
    return build_hwp_bytes(
        table_cells=[(0, 0, "dup"), (1, 0, "B"), (0, 1, "dup"), (1, 1, "D")],
        n_rows=2,
        n_cols=2,
        paras=["paraOne", "paraTwo"],
    )


def _hwpx_fixture() -> bytes:
    return build_hwpx_bytes(
        table_rows=[["dup", "B"], ["dup", "D"]],
        paras=None,
    )


# ── 1. eid 연속성 / 매핑 일치 ──


def test_hwp_editable_eid_contiguous():
    """HWP editable 렌더의 data-eid 는 0..N-1 연속이어야 한다."""
    data = _hwp_fixture()
    html = render_hwp_to_html(data, "hwp", editable=True)
    eids = sorted(int(m) for m in re.findall(r'data-eid="(\d+)"', html))
    assert eids == list(range(len(eids)))
    # 표 자체/행에는 eid 가 없어야 한다.
    assert "<table" in html and 'data-eid' not in html.split("<table", 1)[1].split(">", 1)[0]
    assert "<tr" not in html or '<tr data-eid' not in html


def test_hwpx_editable_eid_contiguous():
    """HWPX editable 렌더의 data-eid 는 0..N-1 연속이어야 한다."""
    data = _hwpx_fixture()
    html = render_hwp_to_html(data, "hwpx", editable=True)
    eids = sorted(int(m) for m in re.findall(r'data-eid="(\d+)"', html))
    assert eids == list(range(len(eids)))
    assert len(eids) == 4  # 2x2 표 셀만(문단 없음)


def test_hwp_render_apply_eid_alignment():
    """렌더 eid→텍스트 매핑이 apply 순회 eid 와 동일해야 한다.

    각 eid 를 자기 자신과 같은 값으로 'edit' 시도하면 변경이 0이어야 하고,
    각 eid 에 고유 새 값을 주면 정확히 그 eid 영역만 그 값으로 바뀌어야 한다.
    """
    data = _hwp_fixture()
    html = render_hwp_to_html(data, "hwp", editable=True)
    mapping = _eid_text_map(html)

    # 동일 텍스트로 edit → 변경 없음
    same_edits = [{"eid": e, "text": t} for e, t in mapping.items() if e <= 5]
    new, changed = apply_block_edits(data, "hwp", same_edits)
    assert changed == 0

    # 각 eid 0..5 에 고유 값 부여
    edits = [{"eid": e, "text": f"V{e}"} for e in range(6)]
    new, changed = apply_block_edits(data, "hwp", edits)
    assert changed == 6
    new_map = _eid_text_map(render_hwp_to_html(new, "hwp", editable=True))
    for e in range(6):
        assert new_map[e] == f"V{e}"


def test_hwpx_render_apply_eid_alignment():
    data = _hwpx_fixture()
    html = render_hwp_to_html(data, "hwpx", editable=True)
    mapping = _eid_text_map(html)

    same_edits = [{"eid": e, "text": t} for e, t in mapping.items()]
    _, changed = apply_block_edits(data, "hwpx", same_edits)
    assert changed == 0

    edits = [{"eid": e, "text": f"V{e}"} for e in range(4)]
    new, changed = apply_block_edits(data, "hwpx", edits)
    assert changed == 4
    new_map = _eid_text_map(render_hwp_to_html(new, "hwpx", editable=True))
    for e in range(4):
        assert new_map[e] == f"V{e}"


# ── 2. 단일 셀 edit → 다른 영역/구조 불변 + 재파싱 ──


def test_hwp_single_cell_edit_isolation():
    data = _hwp_fixture()
    before = svc._extract_tables_from_hwp_bytes(data)
    new, changed = apply_block_edits(data, "hwp", [{"eid": 2, "text": "ONLYB"}])
    assert changed == 1

    # (a) 재파싱 가능: olefile 재오픈 + 텍스트 추출 성공
    assert olefile.isOleFile(io.BytesIO(new))
    text = svc._extract_text_from_hwp_bytes(new)
    assert "ONLYB" in text

    after = svc._extract_tables_from_hwp_bytes(new)
    # (c) 표 구조 불변: 표 수/행수/열수/셀수
    assert len(after) == len(before) == 1
    assert len(after[0]["rows"]) == len(before[0]["rows"])
    assert all(len(r) == len(before[0]["rows"][0]) for r in after[0]["rows"])

    # (b) 해당 셀만 바뀌고 나머지 불변
    # eid 2 = 셀 (1,0) = rows[0][1]
    assert after[0]["rows"][0][1] == "ONLYB"
    assert after[0]["rows"][0][0] == "dup"
    assert after[0]["rows"][1][0] == "dup"
    assert after[0]["rows"][1][1] == "D"


def test_hwpx_single_cell_edit_isolation():
    data = _hwpx_fixture()
    new, changed = apply_block_edits(data, "hwpx", [{"eid": 1, "text": "ONLYB"}])
    assert changed == 1

    # 재파싱: zip + xml 파싱 성공
    with zipfile.ZipFile(io.BytesIO(new), "r") as zf:
        names = zf.namelist()
        assert "Contents/section0.xml" in names
        ET.fromstring(zf.read("Contents/section0.xml"))

    tables = asyncio.run(svc.extract_tables(new, "hwpx"))
    assert len(tables) == 1
    rows = tables[0]["rows"]
    assert len(rows) == 2 and all(len(r) == 2 for r in rows)
    # eid 1 = 첫 행 둘째 셀
    assert rows[0][1] == "ONLYB"
    assert rows[0][0] == "dup"
    assert rows[1][0] == "dup"
    assert rows[1][1] == "D"


# ── 3. 중복 텍스트 셀 한쪽만 edit → 다른 쪽 불변 ──


def test_hwp_duplicate_cell_no_contamination():
    """'dup' 셀이 2개(eid 1, eid 3). eid 1 만 바꾸면 eid 3 은 그대로."""
    data = _hwp_fixture()
    new, changed = apply_block_edits(data, "hwp", [{"eid": 1, "text": "CHANGED"}])
    assert changed == 1
    tables = svc._extract_tables_from_hwp_bytes(new)
    # eid 1 = 셀 (0,0) = rows[0][0], eid 3 = 셀 (0,1) = rows[1][0]
    assert tables[0]["rows"][0][0] == "CHANGED"
    assert tables[0]["rows"][1][0] == "dup"


def test_hwpx_duplicate_cell_no_contamination():
    data = _hwpx_fixture()
    new, changed = apply_block_edits(data, "hwpx", [{"eid": 0, "text": "CHANGED"}])
    assert changed == 1
    tables = asyncio.run(svc.extract_tables(new, "hwpx"))
    assert tables[0]["rows"][0][0] == "CHANGED"
    assert tables[0]["rows"][1][0] == "dup"


# ── 4. HWP 길이 증가 정상 저장 / 과도하면 HwpParseError ──


def test_hwp_grow_text_saved_ok():
    """짧게 늘어난 텍스트도 _build_section_stream 경유로 정상 저장."""
    data = _hwp_fixture()
    longer = "dup" + "_확장된긴텍스트_" * 5
    new, changed = apply_block_edits(data, "hwp", [{"eid": 1, "text": longer}])
    assert changed == 1
    assert olefile.isOleFile(io.BytesIO(new))
    text = svc._extract_text_from_hwp_bytes(new)
    assert longer in text


def test_hwp_too_long_raises():
    """스트림에 담기 불가능할 만큼 긴(비압축성) 텍스트는 HwpParseError."""
    import random

    data = _hwp_fixture()
    # 난수 유니코드로 압축이 거의 안 되는 매우 긴 문자열 생성
    rnd = random.Random(42)
    huge = "".join(chr(0x4E00 + rnd.randint(0, 0x3FFF)) for _ in range(20000))
    with pytest.raises(HwpParseError):
        apply_block_edits(data, "hwp", [{"eid": 1, "text": huge}])


# ── 5. API 엔드포인트(editable 쿼리 + save-blocks) ──


@pytest.mark.asyncio
async def test_api_editable_html_and_save_blocks(client):
    """GET /html?editable=true 로 data-eid 를 받고 POST /save-blocks 로 저장한다."""
    data = _hwpx_fixture()
    up = await client.post(
        "/api/documents/upload",
        files={"file": ("doc.hwpx", data, "application/octet-stream")},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    # editable=true 면 data-eid 포함
    r = await client.get(f"/api/documents/{doc_id}/html", params={"editable": "true"})
    assert r.status_code == 200
    html = r.json()["html"]
    assert 'data-eid="0"' in html
    assert "dup" in html

    # editable 생략 시 data-eid 없음(기존 동작 유지)
    r0 = await client.get(f"/api/documents/{doc_id}/html")
    assert r0.status_code == 200
    assert "data-eid" not in r0.json()["html"]

    # save-blocks: eid 1 만 새 텍스트로
    save = await client.post(
        f"/api/documents/{doc_id}/save-blocks",
        json={"edits": [{"eid": 1, "text": "ONLYB"}]},
    )
    assert save.status_code == 200
    detail = save.json()
    # 새 버전이 추가됨(업로드 v1 + 편집 v2)
    assert any(v["version_number"] == 2 for v in detail["versions"])

    # 저장 결과를 다시 editable 로 받아 eid 1 만 바뀌었는지 확인
    r2 = await client.get(f"/api/documents/{doc_id}/html", params={"editable": "true"})
    new_map = _eid_text_map(r2.json()["html"])
    assert new_map[1] == "ONLYB"
    assert new_map[0] == "dup"
    assert new_map[2] == "dup"


# ── 6. 비교(compare) 화면의 editable 모드 ──


def _eid_orig_map(html: str) -> dict[int, str]:
    """편집용 compare HTML 에서 {eid: data-orig 값} 매핑을 추출한다.

    data-orig 가 있는 영역만 포함한다(변경된 영역).
    """
    out: dict[int, str] = {}
    # data-eid 와 같은 태그 안의 data-orig 를 매칭(속성 순서: eid 가 먼저 옴).
    for m in re.finditer(r'data-eid="(\d+)"[^>]*?data-orig="([^"]*)"', html):
        out[int(m.group(1))] = m.group(2)
    return out


def test_compare_editable_eid_matches_standalone_hwpx():
    """editable compare 의 modified_html eid 집합/순서가 modified 단독 editable 렌더와 동일."""
    orig = _hwpx_fixture()
    mod, _ = apply_block_edits(orig, "hwpx", [{"eid": 1, "text": "ONLYB"}])

    res = render_hwp_compare_html(orig, mod, "hwpx", editable=True)
    mod_html = res["modified_html"]
    standalone = render_hwp_to_html(mod, "hwpx", editable=True)

    e_compare = [int(m) for m in re.findall(r'data-eid="(\d+)"', mod_html)]
    e_standalone = [int(m) for m in re.findall(r'data-eid="(\d+)"', standalone)]
    assert e_compare == e_standalone  # 순서까지 동일

    # original_html 도 동일한 eid 부여(modified 와 1:1 정렬). 단 data-orig/
    # contenteditable 은 없다(원본은 편집/되돌리기 메타 없이 위치 강조용 eid 만).
    orig_html = res["original_html"]
    e_orig = [int(m) for m in re.findall(r'data-eid="(\d+)"', orig_html)]
    assert e_orig == e_compare  # 원본 eid 가 수정본과 같은 순서/집합
    assert "data-orig" not in orig_html
    assert "contenteditable" not in orig_html


def test_compare_editable_eid_matches_standalone_hwp():
    orig = _hwp_fixture()
    mod, _ = apply_block_edits(orig, "hwp", [{"eid": 2, "text": "BB"}])

    res = render_hwp_compare_html(orig, mod, "hwp", editable=True)
    mod_html = res["modified_html"]
    standalone = render_hwp_to_html(mod, "hwp", editable=True)

    e_compare = [int(m) for m in re.findall(r'data-eid="(\d+)"', mod_html)]
    e_standalone = [int(m) for m in re.findall(r'data-eid="(\d+)"', standalone)]
    assert e_compare == e_standalone
    # original_html 도 동일 eid(1:1 정렬), data-orig/contenteditable 없음
    orig_html = res["original_html"]
    e_orig = [int(m) for m in re.findall(r'data-eid="(\d+)"', orig_html)]
    assert e_orig == e_compare
    assert "data-orig" not in orig_html
    assert "contenteditable" not in orig_html


def test_compare_editable_data_orig_only_on_changed_hwpx():
    """변경된 셀에만 data-orig(원본 텍스트)가 들어가고, 안 바뀐 셀엔 없어야 한다."""
    orig = _hwpx_fixture()  # [['dup','B'],['dup','D']]
    mod, _ = apply_block_edits(orig, "hwpx", [{"eid": 1, "text": "ONLYB"}])

    res = render_hwp_compare_html(orig, mod, "hwpx", editable=True)
    mod_html = res["modified_html"]

    orig_map = _eid_orig_map(mod_html)
    # eid 1 만 변경 → data-orig="B"
    assert orig_map == {1: "B"}
    # 변경 셀은 hwp-changed 강조 유지
    assert 'data-eid="1" class="hwp-changed" data-orig="B"' in mod_html


def test_compare_editable_data_orig_only_on_changed_hwp():
    orig = _hwp_fixture()
    # eid 2 = 셀 (1,0), 원본 'B' → 'BB'
    mod, _ = apply_block_edits(orig, "hwp", [{"eid": 2, "text": "BB"}])

    res = render_hwp_compare_html(orig, mod, "hwp", editable=True)
    mod_html = res["modified_html"]
    orig_map = _eid_orig_map(mod_html)
    assert orig_map == {2: "B"}


def test_compare_editable_roundtrip_apply_hwpx():
    """editable compare 로 받은 eid 로 apply_block_edits 하면 정상 반영(eid 일치)."""
    orig = _hwpx_fixture()
    mod, _ = apply_block_edits(orig, "hwpx", [{"eid": 1, "text": "ONLYB"}])

    res = render_hwp_compare_html(orig, mod, "hwpx", editable=True)
    # compare 에서 본 eid 1 을 다시 편집
    new, changed = apply_block_edits(mod, "hwpx", [{"eid": 1, "text": "FINAL"}])
    assert changed == 1
    new_map = _eid_text_map(render_hwp_to_html(new, "hwpx", editable=True))
    assert new_map[1] == "FINAL"
    assert new_map[0] == "dup"
    assert new_map[2] == "dup"


def test_compare_editable_roundtrip_apply_hwp():
    orig = _hwp_fixture()
    mod, _ = apply_block_edits(orig, "hwp", [{"eid": 2, "text": "BB"}])

    res = render_hwp_compare_html(orig, mod, "hwp", editable=True)
    new, changed = apply_block_edits(mod, "hwp", [{"eid": 2, "text": "BBB"}])
    assert changed == 1
    tables = svc._extract_tables_from_hwp_bytes(new)
    # eid 2 = 셀 (1,0) = rows[0][1]
    assert tables[0]["rows"][0][1] == "BBB"
    # 다른 셀 불변
    assert tables[0]["rows"][0][0] == "dup"
    assert tables[0]["rows"][1][1] == "D"


def test_compare_editable_changed_para_keeps_word_span_hwpx():
    """변경된 문단(표 없는 HWPX)은 단어 강조 span 을 유지하며 eid/data-orig 부여."""
    orig = build_hwpx_bytes(table_rows=None, paras=["alpha beta gamma"])
    mod, _ = apply_block_edits(orig, "hwpx", [{"eid": 0, "text": "alpha BETA gamma"}])

    res = render_hwp_compare_html(orig, mod, "hwpx", editable=True)
    mod_html = res["modified_html"]
    # eid 0 부여 + 변경 단어 span 강조 유지 + data-orig 원본 문단
    assert 'data-eid="0"' in mod_html
    assert 'data-orig="alpha beta gamma"' in mod_html
    assert '<span class="hwp-changed">BETA</span>' in mod_html


@pytest.mark.asyncio
async def test_api_compare_editable(client):
    """GET /html/compare?editable=true 가 modified_html 에 data-eid/data-orig 를 부여한다."""
    orig = _hwpx_fixture()
    up = await client.post(
        "/api/documents/upload",
        files={"file": ("doc.hwpx", orig, "application/octet-stream")},
    )
    doc_id = up.json()["id"]

    # 편집 저장으로 v2 생성(셀 1 변경)
    await client.post(
        f"/api/documents/{doc_id}/save-blocks",
        json={"edits": [{"eid": 1, "text": "ONLYB"}]},
    )

    # editable=true 비교
    r = await client.get(
        f"/api/documents/{doc_id}/html/compare",
        params={"base": 1, "editable": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert 'data-eid="1"' in body["modified_html"]
    assert 'data-orig="B"' in body["modified_html"]
    # original_html 도 동일 eid 부여(수정본 셀 클릭 → 원본 같은 셀 강조용).
    # 단 data-orig/contenteditable 은 없다.
    assert 'data-eid="1"' in body["original_html"]
    mod_eids = re.findall(r'data-eid="(\d+)"', body["modified_html"])
    orig_eids = re.findall(r'data-eid="(\d+)"', body["original_html"])
    assert orig_eids == mod_eids
    assert "data-orig" not in body["original_html"]
    assert "contenteditable" not in body["original_html"]

    # editable 생략 시 기존 동작(eid 없음)
    r0 = await client.get(
        f"/api/documents/{doc_id}/html/compare", params={"base": 1}
    )
    assert "data-eid" not in r0.json()["modified_html"]
