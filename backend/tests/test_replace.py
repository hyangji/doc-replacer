"""엑셀 기반 일괄 교체 및 매핑 로직 테스트."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_sample_excel, create_sample_hwpx

pytestmark = pytest.mark.asyncio


async def _upload_and_get_id(client: AsyncClient, texts: list[str] | None = None) -> int:
    """HWPX 업로드 후 문서 ID를 반환하는 헬퍼."""
    data = create_sample_hwpx(texts)
    resp = await client.post(
        "/api/documents/upload",
        files={"file": ("doc.hwpx", data, "application/octet-stream")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Excel replace
# ---------------------------------------------------------------------------


async def test_replace_with_excel(client: AsyncClient):
    """엑셀 파일 업로드로 일괄 교체 시 교체 건수와 새 버전 번호가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(
        client, ["서울특별시 강남구", "2024년도 사업계획"]
    )

    excel_bytes = create_sample_excel(
        rows=[("도시명", "서울특별시", "부산광역시")],
    )
    resp = await client.post(
        f"/api/documents/{doc_id}/replace/excel",
        files={"file": ("mapping.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["replaced_count"] >= 1
    assert body["version_number"] == 2


async def test_replace_preview(client: AsyncClient):
    """엑셀 파일 미리보기 시 매핑 정보가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client)

    excel_bytes = create_sample_excel()
    resp = await client.post(
        f"/api/documents/{doc_id}/replace/preview",
        files={"file": ("mapping.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "headers" in body
    assert "replacements" in body
    assert len(body["replacements"]) >= 1
    assert body["total_rows"] >= 1


async def test_replace_with_invalid_excel(client: AsyncClient):
    """잘못된 엑셀 파일 업로드 시 에러가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client)

    resp = await client.post(
        f"/api/documents/{doc_id}/replace/excel",
        files={"file": ("bad.txt", b"not excel", "text/plain")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Excel mapping unit test
# ---------------------------------------------------------------------------


def test_excel_mapping():
    """엑셀 데이터를 테이블 셀에 매핑하는 로직이 정확히 동작해야 한다."""
    from app.services.excel_service import map_excel_to_tables  # noqa: E402

    replacements = [
        {"field_name": "도시명", "old_value": "서울", "new_value": "부산"},
        {"field_name": "구명", "old_value": "강남", "new_value": "해운대"},
    ]
    tables = [
        {
            "index": 0,
            "rows": [["항목", "값"], ["도시명", "서울특별시"], ["구명", "강남구"]],
            "headers": ["항목", "값"],
        }
    ]

    mapped = map_excel_to_tables(replacements, tables)
    assert len(mapped) == 2

    # "서울"은 "서울특별시" 셀에서 발견되어야 함
    seoul_matches = mapped[0]["matched_tables"]
    assert len(seoul_matches) >= 1
    assert seoul_matches[0]["table_index"] == 0

    # "강남"은 "강남구" 셀에서 발견되어야 함
    gangnam_matches = mapped[1]["matched_tables"]
    assert len(gangnam_matches) >= 1
