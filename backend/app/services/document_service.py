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


async def create_preview_version(
    db: AsyncSession,
    document: Document,
    new_file_data: bytes,
    new_content_text: str | None,
    changes_summary: str,
) -> DocumentVersion:
    """Create a new version WITHOUT updating the document's current content.

    Used for Excel batch replace: the user reviews the diff first,
    and only when they explicitly click "Save" does the document update.
    """
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

    # NOTE: document.file_data / content_text are NOT updated here.
    # The user must explicitly save from the Diff view.

    await db.commit()
    await db.refresh(version)
    return version


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
    old_text = await hwp_service.get_text_content(document.file_data, ft)
    tables = await hwp_service.extract_tables(document.file_data, ft)
    mapped = map_excel_to_tables(replacements, tables)

    current_data = document.file_data
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
            f"일괄 교체: {len(replacements)}건 요청, "
            f"{applied_count}건 매칭, {total_count}건 수정"
        )
        version = await create_preview_version(db, document, current_data, new_content, summary)
        return total_count, version.version_number

    return 0, 0


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
    """에디터에서 수정한 내용을 HWPX 파일에 저장."""
    if document.file_type != FileType.HWPX:
        raise DocumentServiceError("현재 HWPX 파일만 저장을 지원합니다.")
    if not document.file_data:
        raise DocumentServiceError("파일 데이터가 없습니다.")

    new_data = await hwp_service.save_file(document.file_data, content)
    await create_version(db, document, new_data, content, "에디터에서 직접 수정")
    await db.refresh(document)
    return document


# ── Delete ──


async def delete_document(db: AsyncSession, document: Document) -> None:
    """Delete a document (DB only, no filesystem cleanup needed)."""
    await db.delete(document)
    await db.commit()
