"""Document management service - orchestrates file upload, storage, and DB operations."""

import os
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.document import (
    Document,
    DocumentVersion,
    FileType,
    ReplacementLog,
    ReplacementType,
)
from app.services.hwp_service import (
    HwpConversionError,
    HwpParseError,
    HwpService,
    detect_file_type,
)

ALLOWED_EXTENSIONS = {".hwp", ".hwpx"}

hwp_service = HwpService()


class DocumentServiceError(Exception):
    """Base exception for document service errors."""


# ── Upload ──


async def create_document(db: AsyncSession, file: UploadFile) -> Document:
    """Upload and create a new document record."""
    if not file.filename:
        raise DocumentServiceError("파일 이름이 없습니다.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentServiceError(
            f"지원하지 않는 파일 형식입니다: {ext}. "
            f"허용 형식: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_type = detect_file_type(file.filename)
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise DocumentServiceError(
            f"파일 크기가 제한을 초과했습니다. "
            f"최대: {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB"
        )

    # Extract text content
    content_text = None
    if file_type in ("hwpx", "hwp"):
        try:
            content_text = await hwp_service.get_text_content(content, file_type)
        except (HwpParseError, HwpConversionError):
            pass

    # Create document with file data stored in DB
    doc = Document(
        filename=f"current{ext}",
        original_filename=file.filename,
        file_type=FileType(file_type),
        file_path="db",  # 파일이 DB에 저장됨을 표시
        file_data=content,
        content_text=content_text,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Create initial version (v1)
    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        file_path="db",
        file_data=content,
        content_text=content_text,
        changes_summary="초기 업로드",
    )
    db.add(version)
    await db.commit()

    return doc


# ── Read ──


async def get_document(db: AsyncSession, document_id: int) -> Document | None:
    """Get a document by ID with versions loaded."""
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.versions))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_documents(db: AsyncSession) -> list[Document]:
    """List all documents ordered by creation date."""
    stmt = select(Document).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Version management ──


async def get_latest_version(db: AsyncSession, document_id: int) -> DocumentVersion | None:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_version(
    db: AsyncSession,
    document: Document,
    new_file_data: bytes,
    new_content_text: str | None,
    changes_summary: str,
) -> DocumentVersion:
    """Create a new version for a document."""
    latest = await get_latest_version(db, document.id)
    next_version = (latest.version_number + 1) if latest else 1

    version = DocumentVersion(
        document_id=document.id,
        version_number=next_version,
        file_path="db",
        file_data=new_file_data,
        content_text=new_content_text,
        changes_summary=changes_summary,
    )
    db.add(version)

    # Update document current file
    document.file_data = new_file_data
    document.content_text = new_content_text
    document.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(version)
    return version


async def get_version_by_number(
    db: AsyncSession, document_id: int, version_number: int
) -> DocumentVersion | None:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .where(DocumentVersion.version_number == version_number)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_versions(db: AsyncSession, document_id: int) -> list[DocumentVersion]:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Replace (Excel-based batch) ──


async def replace_in_document(
    db: AsyncSession,
    document: Document,
    replacements: list[dict],
) -> tuple[int, int]:
    """Apply multiple text replacements to a document.

    Args:
        replacements: list of {"field_name": str, "old_value": str, "new_value": str}

    Returns (total_replaced_count, new_version_number).
    """
    from app.services.excel_service import build_replacement_diff, map_excel_to_tables

    if document.file_type not in (FileType.HWPX, FileType.HWP):
        raise DocumentServiceError("현재 HWP/HWPX 파일만 수정을 지원합니다.")

    if not document.file_data:
        raise DocumentServiceError("파일 데이터가 없습니다.")

    ft = document.file_type.value

    # 대비표 적용은 '항상 원본(v1) 기준'으로 한다. document.file_data(=최신 상태)
    # 를 기준으로 하면 엑셀을 여러 번 적용할 때 변경이 누적되어 사용자에게 혼란을
    # 준다. v1을 base로 삼으면 create_version 이 latest=「v1+이 엑셀」을 만들고,
    # get_diff(v1 vs latest) 는 항상 '이 엑셀 적용분'만 보여준다(누적 제거).
    original_version = await get_version_by_number(db, document.id, 1)
    base_data = (
        original_version.file_data
        if (original_version and original_version.file_data)
        else document.file_data
    )

    old_text = await hwp_service.get_text_content(base_data, ft)
    tables = await hwp_service.extract_tables(base_data, ft)
    mapped = map_excel_to_tables(replacements, tables)

    current_data = base_data
    total_count = 0

    for r in replacements:
        new_data, count = hwp_service.replace_text(
            current_data, r["old_value"], r["new_value"], file_type=ft
        )
        total_count += count
        if count > 0:
            log = ReplacementLog(
                document_id=document.id,
                field_name=r["field_name"],
                old_value=r["old_value"],
                new_value=r["new_value"],
                replacement_type=ReplacementType.EXCEL,
            )
            db.add(log)
            current_data = new_data

    if total_count > 0:
        new_content = await hwp_service.get_text_content(current_data, ft)
        diff_records = build_replacement_diff(replacements, old_text, new_content)
        applied_count = sum(1 for d in diff_records if d["applied"])
        summary = (
            f"일괄 교체(원본 기준 적용): {len(replacements)}건 요청, "
            f"{applied_count}건 매칭, {total_count}건 수정"
        )
        # 대비표 적용을 즉시 본문(document.content_text/file_data)에 반영한다.
        # 이렇게 해야 편집 탭이 적용분을 보여주고, HWP 직접수정 저장이
        # 최신 버전을 기준으로 손편집만 누적 합성한다.
        version = await create_version(db, document, current_data, new_content, summary)
        return total_count, version.version_number

    return 0, 0


async def reset_to_original(db: AsyncSession, document: Document) -> Document:
    """문서를 원본(v1) 상태로 초기화한다.

    v1 의 file_data/content_text 로 새 버전을 생성해 latest 로 만든다.
    이렇게 하면 document.file_data/content_text 가 v1 내용으로 갱신되고,
    get_diff(v1 vs latest=v1내용) 는 '변경 없음'이 된다(누적·손편집 전부 해제).
    """
    original_version = await get_version_by_number(db, document.id, 1)
    if not original_version or not original_version.file_data:
        raise DocumentServiceError("원본 버전을 찾을 수 없습니다.")

    await create_version(
        db,
        document,
        original_version.file_data,
        original_version.content_text,
        "원본으로 초기화",
    )
    await db.refresh(document)
    return document


# ── Search / Replace (delegates to search_service) ──


async def search_in_document(
    document: Document,
    query: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
) -> list[dict]:
    """Search text in a document. Delegates to search_service."""
    from app.services.search_service import search_in_document as _search
    return await _search(document, query, case_sensitive, use_regex)


async def replace_text_in_document(
    db: AsyncSession,
    document: Document,
    search: str,
    replace: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
) -> tuple[int, int]:
    """Search and replace text. Delegates to search_service."""
    from app.services.search_service import replace_text_in_document as _replace
    return await _replace(db, document, search, replace, case_sensitive, use_regex)


# ── Diff (delegates to diff_service) ──


async def get_diff(
    db: AsyncSession,
    document: Document,
    version_number: int | None = None,
) -> dict:
    """Get diff between original and a version. Delegates to diff_service."""
    from app.services.diff_service import get_diff as _get_diff
    return await _get_diff(db, document, version_number)


# ── Revert (delegates to diff_service) ──


async def revert_to_version(
    db: AsyncSession,
    document: Document,
    version_number: int,
) -> Document:
    """Revert document to a specific version. Delegates to diff_service."""
    from app.services.diff_service import revert_to_version as _revert
    return await _revert(db, document, version_number)


# ── Save content ──


async def save_document_content(
    db: AsyncSession,
    document: Document,
    content: str,
) -> Document:
    """에디터에서 수정한 내용을 HWP/HWPX 파일에 저장.

    - HWPX: 원본 ZIP의 <t> 텍스트 요소들을 새 텍스트 라인으로 순서대로 덮어쓴다.
    - HWP : 최신 버전을 기준으로 라인 단위 diff를 구해, 바뀐 라인마다
            replace_text(old_line → new_line)로 바이너리를 치환한다.
            (대비표 적용분 위에 손편집만 누적되도록 최신 버전을 기준으로 함)
    """
    import logging

    logger = logging.getLogger(__name__)

    if not document.file_data:
        raise DocumentServiceError("파일 데이터가 없습니다.")

    # ── HWPX: 기존 동작 그대로 ──
    if document.file_type == FileType.HWPX:
        new_data = await hwp_service.save_file(document.file_data, content)
        await create_version(db, document, new_data, content, "에디터에서 직접 수정")
        await db.refresh(document)
        return document

    # ── HWP 바이너리: 라인 단위 diff → replace_text 누적 치환 ──
    if document.file_type == FileType.HWP:
        # 최신 버전(대비표 적용분 포함)을 기준으로 삼아 손편집을 그 위에 누적한다.
        latest = await get_latest_version(db, document.id)
        base_data = latest.file_data if latest and latest.file_data else document.file_data

        old_text = await hwp_service.get_text_content(base_data, "hwp")
        old_lines = old_text.split("\n")
        new_lines = content.split("\n")

        current_data = base_data
        changed_count = 0

        # 인덱스로 두 리스트를 짝지어 비교한다. 라인 내용이 바뀌었고
        # 기존 라인이 공백이 아닌 경우에만 바이너리 치환을 적용한다.
        for idx, old_line in enumerate(old_lines):
            if idx >= len(new_lines):
                # 라인이 삭제된 경우. 바이너리에서 구조적 삭제는 이번 범위 밖이므로
                # 치환하지 않고 로깅만 한다(값 치환 중심 앱이라 허용).
                logger.info(
                    "HWP 직접수정: 라인 삭제는 미지원(무시) idx=%s, old=%r", idx, old_line
                )
                continue
            new_line = new_lines[idx]
            if old_line != new_line and old_line.strip():
                current_data, _ = hwp_service.replace_text(
                    current_data, old_line, new_line, file_type="hwp"
                )
                changed_count += 1

        # 새로 추가된 라인(인덱스 초과분)은 구조적 삽입이 어려워 이번 범위에서는 무시.
        if len(new_lines) > len(old_lines):
            logger.info(
                "HWP 직접수정: 추가된 라인 %s개는 미지원(무시)",
                len(new_lines) - len(old_lines),
            )

        if changed_count == 0:
            logger.info("HWP 직접수정: 변경된 라인이 없습니다.")

        await create_version(
            db, document, current_data, content, "에디터에서 직접 수정"
        )
        await db.refresh(document)
        return document

    raise DocumentServiceError("현재 HWP/HWPX 파일만 저장을 지원합니다.")


# ── Save block edits (구조 보존 인라인 편집) ──


async def save_document_blocks(
    db: AsyncSession,
    document: Document,
    edits: list[dict],
) -> Document:
    """data-eid 기반 영역 텍스트 편집을 HWP/HWPX 파일에 무손실 반영하고 저장한다.

    save_document_content 를 미러링한다:
      - 최신 버전(대비표 적용분 포함)을 기준으로 손편집을 누적한다.
      - hwp_service.apply_block_edits 로 새 file_data 를 만든다(표 구조·서식 불변).
      - content_text 를 평문으로 재추출하고 새 DocumentVersion 을 생성한다.

    edits: [{"eid": int, "text": str}, ...]
    """
    from app.services.hwp_service import apply_block_edits

    if document.file_type not in (FileType.HWPX, FileType.HWP):
        raise DocumentServiceError("현재 HWP/HWPX 파일만 저장을 지원합니다.")

    if not document.file_data:
        raise DocumentServiceError("파일 데이터가 없습니다.")

    ft = document.file_type.value

    # 최신 버전(대비표 적용분 포함)을 기준으로 손편집을 그 위에 누적한다.
    latest = await get_latest_version(db, document.id)
    base_data = latest.file_data if latest and latest.file_data else document.file_data
    base_data = bytes(base_data)

    try:
        new_data, changed = apply_block_edits(base_data, ft, edits)
    except HwpParseError as e:
        raise DocumentServiceError(str(e))

    try:
        new_content = await hwp_service.get_text_content(new_data, ft)
    except (HwpParseError, HwpConversionError):
        new_content = document.content_text

    summary = f"인라인 편집: {changed}개 영역 수정"
    await create_version(db, document, new_data, new_content, summary)
    await db.refresh(document)
    return document


# ── Delete ──


async def delete_document(db: AsyncSession, document: Document) -> None:
    """Delete a document (DB only, no filesystem cleanup needed)."""
    await db.delete(document)
    await db.commit()
