"""검색/치환 API 테스트."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_sample_hwpx

pytestmark = pytest.mark.asyncio


async def _upload_and_get_id(client: AsyncClient, texts: list[str] | None = None) -> int:
    data = create_sample_hwpx(texts)
    resp = await client.post(
        "/api/documents/upload",
        files={"file": ("doc.hwpx", data, "application/octet-stream")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def test_search_basic(client: AsyncClient):
    """기본 검색 시 일치하는 결과가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client, ["서울특별시 강남구", "부산광역시 해운대구"])

    resp = await client.post(
        f"/api/documents/{doc_id}/search",
        json={"query": "강남구"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] >= 1
    assert body["matches"][0]["match"] == "강남구"


async def test_search_case_sensitive(client: AsyncClient):
    """대소문자 구분 검색이 정확히 동작해야 한다."""
    doc_id = await _upload_and_get_id(client, ["Hello World", "hello world"])

    # 대소문자 구분 OFF (기본값) — 둘 다 매칭
    resp = await client.post(
        f"/api/documents/{doc_id}/search",
        json={"query": "hello", "case_sensitive": False},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 2

    # 대소문자 구분 ON — 소문자만 매칭
    resp = await client.post(
        f"/api/documents/{doc_id}/search",
        json={"query": "hello", "case_sensitive": True},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 1


async def test_search_regex(client: AsyncClient):
    """정규식 검색이 정확히 동작해야 한다."""
    doc_id = await _upload_and_get_id(client, ["2024년도 사업계획", "2025년도 예산안"])

    resp = await client.post(
        f"/api/documents/{doc_id}/search",
        json={"query": r"20\d{2}년도", "regex": True},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 2


# ---------------------------------------------------------------------------
# Replace
# ---------------------------------------------------------------------------


async def test_replace_single(client: AsyncClient):
    """단일 치환 시 교체 건수와 새 버전이 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client, ["서울특별시 강남구"])

    resp = await client.post(
        f"/api/documents/{doc_id}/replace-text",
        json={"search": "강남구", "replace": "서초구"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["replaced_count"] == 1
    assert body["version_number"] == 2


async def test_replace_all(client: AsyncClient):
    """전체 치환 시 모든 일치 항목이 교체되어야 한다."""
    doc_id = await _upload_and_get_id(
        client, ["서울 강남", "서울 서초", "서울 송파"]
    )

    resp = await client.post(
        f"/api/documents/{doc_id}/replace-text",
        json={"search": "서울", "replace": "부산"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["replaced_count"] == 3
    assert body["version_number"] == 2
