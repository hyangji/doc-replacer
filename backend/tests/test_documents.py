"""문서 업로드, 조회, 저장, 버전 관리 API 테스트."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_sample_hwpx

pytestmark = pytest.mark.asyncio


async def _upload_hwpx(client: AsyncClient, texts: list[str] | None = None) -> dict:
    """HWPX 파일을 업로드하고 응답 JSON을 반환하는 헬퍼."""
    data = create_sample_hwpx(texts)
    resp = await client.post(
        "/api/documents/upload",
        files={"file": ("test.hwpx", data, "application/octet-stream")},
    )
    return resp


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


async def test_upload_document(client: AsyncClient):
    """HWPX 파일 업로드 시 201 응답과 문서 ID가 반환되어야 한다."""
    resp = await _upload_hwpx(client)
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["original_filename"] == "test.hwpx"
    assert body["file_type"] == "hwpx"


async def test_upload_invalid_file(client: AsyncClient):
    """지원하지 않는 파일 형식 업로드 시 400 에러가 반환되어야 한다."""
    resp = await client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    assert "지원하지 않는" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_documents(client: AsyncClient):
    """문서 목록 조회 시 업로드된 문서가 포함되어야 한다."""
    await _upload_hwpx(client)
    await _upload_hwpx(client)

    resp = await client.get("/api/documents/")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 2


# ---------------------------------------------------------------------------
# Get document
# ---------------------------------------------------------------------------


async def test_get_document(client: AsyncClient):
    """특정 문서 상세 조회 시 내용과 버전 정보가 포함되어야 한다."""
    upload_resp = await _upload_hwpx(client)
    doc_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc_id
    assert body["original_filename"] == "test.hwpx"
    assert "versions" in body
    assert len(body["versions"]) >= 1


async def test_get_document_not_found(client: AsyncClient):
    """존재하지 않는 문서 조회 시 404 에러가 반환되어야 한다."""
    resp = await client.get("/api/documents/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


async def test_save_document(client: AsyncClient):
    """문서 저장 시 200 응답이 반환되어야 한다."""
    upload_resp = await _upload_hwpx(client)
    doc_id = upload_resp.json()["id"]

    resp = await client.post(f"/api/documents/{doc_id}/save")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc_id


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


async def test_get_versions(client: AsyncClient):
    """버전 이력 조회 시 최소 1개의 초기 버전이 반환되어야 한다."""
    upload_resp = await _upload_hwpx(client)
    doc_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/documents/{doc_id}/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["changes_summary"] == "초기 업로드"
