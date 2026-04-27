"""테스트 공통 fixtures.

pytest-asyncio + SQLite 메모리 DB + httpx.AsyncClient 기반 테스트 환경 구성.
"""

import io
import os
import zipfile
from xml.etree import ElementTree as ET

import openpyxl
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.document import Base

# ---------------------------------------------------------------------------
# DB: 테스트용 SQLite async (aiosqlite)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session():
    """각 테스트마다 새로운 인메모리 DB 세션을 제공한다."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_test() as session:
        yield session

    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# FastAPI TestClient (httpx.AsyncClient)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, tmp_path):
    """테스트용 FastAPI AsyncClient. DB 의존성과 UPLOAD_DIR을 오버라이드한다."""
    from app.config import settings
    from app.main import app

    # DB 의존성 오버라이드
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # 업로드 디렉토리를 임시 경로로 교체
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path / "uploads")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    # 원복
    settings.UPLOAD_DIR = original_upload_dir
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 샘플 HWPX 파일 생성
# ---------------------------------------------------------------------------

SAMPLE_TEXT_LINES = ["도시계획 제안서", "서울특별시 강남구", "2024년도 사업계획"]


def _build_section_xml(texts: list[str]) -> bytes:
    """최소한의 유효 HWPX 섹션 XML을 생성한다."""
    ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    sec_ns = "http://www.hancom.co.kr/hwpml/2011/section"
    root = ET.Element(f"{{{sec_ns}}}sec")
    for text in texts:
        p = ET.SubElement(root, f"{{{ns}}}p")
        run = ET.SubElement(p, f"{{{ns}}}run")
        t = ET.SubElement(run, f"{{{ns}}}t")
        t.text = text
    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")


def create_sample_hwpx(texts: list[str] | None = None) -> bytes:
    """테스트용 HWPX(ZIP+XML) 파일 바이트를 생성한다."""
    if texts is None:
        texts = SAMPLE_TEXT_LINES

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", _build_section_xml(texts))
        zf.writestr("META-INF/container.xml", "<container/>")
    buf.seek(0)
    return buf.read()


@pytest.fixture
def sample_hwpx_bytes():
    """기본 HWPX 파일 바이트를 반환한다."""
    return create_sample_hwpx()


@pytest.fixture
def sample_hwpx_file(tmp_path, sample_hwpx_bytes):
    """디스크에 저장된 HWPX 파일 경로를 반환한다."""
    path = tmp_path / "test_document.hwpx"
    path.write_bytes(sample_hwpx_bytes)
    return str(path)


# ---------------------------------------------------------------------------
# 샘플 엑셀 파일 생성
# ---------------------------------------------------------------------------


def create_sample_excel(
    rows: list[tuple[str, str, str]] | None = None,
    headers: tuple[str, str, str] = ("필드명", "원본", "수정"),
) -> bytes:
    """테스트용 엑셀(.xlsx) 파일 바이트를 생성한다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    if rows is None:
        rows = [
            ("도시명", "서울특별시", "부산광역시"),
            ("구명", "강남구", "해운대구"),
        ]
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.fixture
def sample_excel_bytes():
    """기본 엑셀 파일 바이트를 반환한다."""
    return create_sample_excel()
