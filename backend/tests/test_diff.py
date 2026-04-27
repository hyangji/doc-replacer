"""Diff 생성 및 되돌리기 API 테스트."""

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
# Diff
# ---------------------------------------------------------------------------


async def test_generate_diff(client: AsyncClient):
    """Diff 생성 시 원본/수정본 텍스트가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client, ["서울특별시 강남구"])

    # 치환으로 v2 생성
    await client.post(
        f"/api/documents/{doc_id}/replace-text",
        json={"search": "강남구", "replace": "서초구"},
    )

    resp = await client.get(f"/api/documents/{doc_id}/diff")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == doc_id
    assert "강남구" in body["original_text"]
    assert "서초구" in body["modified_text"]
    assert body["version_number"] == 2


async def test_generate_diff_specific_version(client: AsyncClient):
    """특정 버전의 Diff를 조회할 수 있어야 한다."""
    doc_id = await _upload_and_get_id(client, ["서울특별시 강남구"])

    # v1만 있는 상태에서 diff 조회
    resp = await client.get(f"/api/documents/{doc_id}/diff", params={"version": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_number"] == 1


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------


async def test_revert_document(client: AsyncClient):
    """이전 버전으로 되돌리기 시 원본 내용이 복원되어야 한다."""
    doc_id = await _upload_and_get_id(client, ["서울특별시 강남구"])

    # v2 생성 (치환)
    await client.post(
        f"/api/documents/{doc_id}/replace-text",
        json={"search": "강남구", "replace": "서초구"},
    )

    # v1으로 되돌리기
    resp = await client.post(
        f"/api/documents/{doc_id}/revert",
        params={"version": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc_id
    # 되돌린 후 content_text에 원본 텍스트가 있어야 함
    if body.get("content_text"):
        assert "강남구" in body["content_text"]


async def test_revert_not_found(client: AsyncClient):
    """존재하지 않는 버전으로 되돌리기 시 400 에러가 반환되어야 한다."""
    doc_id = await _upload_and_get_id(client)

    resp = await client.post(
        f"/api/documents/{doc_id}/revert",
        params={"version": 999},
    )
    assert resp.status_code == 400
    assert "찾을 수 없습니다" in resp.json()["detail"]
