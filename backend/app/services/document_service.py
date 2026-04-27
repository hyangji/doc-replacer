"""Document management service - orchestrates file upload, storage, and DB operations."""

import os
from datetime import datetime, timezone

import aiofiles
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


async def create_document(
    db: AsyncSession,
    file: UploadFile,
) -> Document:
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

    # Save to temp first
    temp_path = await hwp_service.save_upload_to_temp(content, ext)

    # Create DB record to get the document ID
    doc = Document(
        filename=f"current{ext}",
        original_filename=file.filename,
        file_type=FileType(file_type),
        file_path="",  # will be set after structured storage
        content_text=None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Move to structured storage: uploads/{id}/original.hwpx, current.hwpx
    original_path, current_path = hwp_service.move_to_document_storage(
        temp_path, doc.id, ext
    )
    doc.file_path = current_path

    # Extract text content
    content_text = None
    if file_type == "hwpx":
        try:
            content_text = await hwp_service.get_text_content(current_path)
        except (HwpParseError, HwpConversionError):
            pass
    elif file_type == "hwp":
        pass  # HWP binary not yet supported

    doc.content_text = content_text
    await db.commit()
    await db.refresh(doc)

    # Create initial version (v1)
    v1_path = hwp_service.save_version_file(current_path, doc.id, 1, ext)
    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        file_path=v1_path,
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
    new_file_path: str,
    new_content_text: str | None,
    changes_summary: str,
) -> DocumentVersion:
    """Create a new version for a document."""
    latest = await get_latest_version(db, document.id)
    next_version = (latest.version_number + 1) if latest else 1

    ext = os.path.splitext(document.file_path)[1].lower() or ".hwpx"
    version_path = hwp_service.save_version_file(
        new_file_path, document.id, next_version, ext
    )

    version = DocumentVersion(
        document_id=document.id,
        version_number=next_version,
        file_path=version_path,
        content_text=new_content_text,
        changes_summary=changes_summary,
    )
    db.add(version)

    # Update document current file
    doc_dir = hwp_service.get_document_dir(document.id)
    current_path = os.path.join(doc_dir, f"current{ext}")
    import shutil
    shutil.copy2(new_file_path, current_path)

    document.file_path = current_path
    document.content_text = new_content_text
    document.updated_at = datetime.now(timezone.utc)

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

    Supports both full-text replacements and table-targeted replacements.
    Tracks before/after diff for each replacement and logs all changes.

    Args:
        replacements: list of {"field_name": str, "old_value": str, "new_value": str}

    Returns (total_replaced_count, new_version_number).
    """
    from app.services.excel_service import build_replacement_diff, map_excel_to_tables

    if document.file_type != FileType.HWPX:
        raise DocumentServiceError("현재 HWPX 파일만 수정을 지원합니다.")

    # Capture pre-replacement text for diff
    old_text = await hwp_service.get_text_content(document.file_path)

    # Map replacements to table cells for visibility
    tables = await hwp_service.extract_tables(document.file_path)
    mapped = map_excel_to_tables(replacements, tables)

    # Apply replacements sequentially
    current_path = document.file_path
    total_count = 0

    for r in replacements:
        new_path, count = hwp_service.replace_text(
            current_path, r["old_value"], r["new_value"]
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
            current_path = new_path

    if total_count > 0:
        new_content = await hwp_service.get_text_content(current_path)

        # Build diff records for the summary
        diff_records = build_replacement_diff(replacements, old_text, new_content)
        applied_count = sum(1 for d in diff_records if d["applied"])

        summary = (
            f"일괄 교체: {len(replacements)}건 요청, "
            f"{applied_count}건 매칭, {total_count}건 수정"
        )
        version = await create_version(db, document, current_path, new_content, summary)
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


# ── Delete ──


async def delete_document(db: AsyncSession, document: Document) -> None:
    """Delete a document and its files."""
    import shutil
    doc_dir = hwp_service.get_document_dir(document.id)

    await db.delete(document)
    await db.commit()

    if os.path.exists(doc_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)
