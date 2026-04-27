from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.document import (
    ConvertRequest,
    ConvertResponse,
    DiffResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentUploadResponse,
    ExcelPreviewResponse,
    ReplacementRequest,
    ReplacementResponse,
    ReplaceTextRequest,
    ReplaceTextResponse,
    SearchRequest,
    SearchResult,
    VersionSummary,
)
from app.services import document_service
from app.services.document_service import DocumentServiceError
from app.services.diff_service import DiffServiceError
from app.services.excel_service import ExcelParseError, ExcelServiceError

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def _get_document_or_404(document_id: int, db: AsyncSession):
    doc = await document_service.get_document(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"문서를 찾을 수 없습니다: {document_id}",
        )
    return doc


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="문서 업로드",
)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    try:
        doc = await document_service.create_document(db, file)
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DocumentUploadResponse.model_validate(doc)


@router.get(
    "/",
    response_model=list[DocumentListItem],
    summary="문서 목록 조회",
)
async def list_documents(
    db: AsyncSession = Depends(get_db),
) -> list[DocumentListItem]:
    docs = await document_service.list_documents(db)
    return [DocumentListItem.model_validate(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="문서 상세 조회",
)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await _get_document_or_404(document_id, db)
    return DocumentDetail.model_validate(doc)


# ── Excel-based replacement ──


@router.post(
    "/{document_id}/replace/preview",
    response_model=ExcelPreviewResponse,
    summary="엑셀 파일 미리보기 (교체 전 확인)",
)
async def preview_excel_replacement(
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ExcelPreviewResponse:
    """Upload an Excel file and preview the replacement mappings before applying."""
    await _get_document_or_404(document_id, db)

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="엑셀 파일(.xlsx)만 업로드 가능합니다.",
        )

    content = await file.read()
    try:
        from app.services.excel_service import parse_excel_preview
        preview = parse_excel_preview(content)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    return ExcelPreviewResponse(**preview)


@router.post(
    "/{document_id}/replace/excel",
    response_model=ReplacementResponse,
    summary="엑셀 파일 업로드 후 일괄 교체",
)
async def replace_from_excel(
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ReplacementResponse:
    """Upload an Excel file with replacement mappings and apply them to the document."""
    doc = await _get_document_or_404(document_id, db)

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="엑셀 파일(.xlsx)만 업로드 가능합니다.",
        )

    content = await file.read()
    try:
        from app.services.excel_service import parse_replacement_excel
        replacements = parse_replacement_excel(content)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    try:
        count, version_number = await document_service.replace_in_document(
            db, doc, replacements
        )
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return ReplacementResponse(
        document_id=document_id, replaced_count=count, version_number=version_number
    )


@router.post(
    "/{document_id}/replace",
    response_model=ReplacementResponse,
    summary="JSON 기반 일괄 교체",
)
async def replace_fields(
    document_id: int,
    body: ReplacementRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplacementResponse:
    doc = await _get_document_or_404(document_id, db)
    try:
        replacements = [r.model_dump() for r in body.replacements]
        count, version_number = await document_service.replace_in_document(
            db, doc, replacements
        )
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ReplacementResponse(
        document_id=document_id, replaced_count=count, version_number=version_number
    )


# ── Search / Replace ──


@router.post(
    "/{document_id}/search",
    response_model=SearchResult,
    summary="문서 내 검색",
)
async def search_document(
    document_id: int,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SearchResult:
    doc = await _get_document_or_404(document_id, db)
    matches = await document_service.search_in_document(
        doc, body.query, body.case_sensitive, body.regex
    )
    return SearchResult(
        document_id=document_id,
        query=body.query,
        matches=matches,
        total_count=len(matches),
    )


@router.post(
    "/{document_id}/replace-text",
    response_model=ReplaceTextResponse,
    summary="검색/치환",
)
async def replace_text(
    document_id: int,
    body: ReplaceTextRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplaceTextResponse:
    doc = await _get_document_or_404(document_id, db)
    try:
        count, version_number = await document_service.replace_text_in_document(
            db, doc, body.search, body.replace, body.case_sensitive, body.regex
        )
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ReplaceTextResponse(
        document_id=document_id, replaced_count=count, version_number=version_number
    )


# ── Diff / Version ──


@router.get(
    "/{document_id}/diff",
    response_model=DiffResponse,
    summary="원본 vs 수정본 비교",
)
async def get_diff(
    document_id: int,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> DiffResponse:
    doc = await _get_document_or_404(document_id, db)
    try:
        diff_data = await document_service.get_diff(db, doc, version)
    except (DocumentServiceError, DiffServiceError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DiffResponse(**diff_data)


@router.post(
    "/{document_id}/revert",
    response_model=DocumentDetail,
    summary="이전 버전으로 되돌리기",
)
async def revert_document(
    document_id: int,
    version: int,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await _get_document_or_404(document_id, db)
    try:
        doc = await document_service.revert_to_version(db, doc, version)
    except (DocumentServiceError, DiffServiceError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    doc = await _get_document_or_404(document_id, db)
    return DocumentDetail.model_validate(doc)


@router.post(
    "/{document_id}/save",
    response_model=DocumentDetail,
    status_code=status.HTTP_200_OK,
    summary="문서 저장",
)
async def save_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await _get_document_or_404(document_id, db)
    return DocumentDetail.model_validate(doc)


@router.post(
    "/{document_id}/convert",
    response_model=ConvertResponse,
    summary="파일 변환 (Word/PDF)",
)
async def convert_document(
    document_id: int,
    body: ConvertRequest,
    db: AsyncSession = Depends(get_db),
) -> ConvertResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="파일 변환 기능은 Phase 3에서 구현 예정입니다.",
    )


@router.get(
    "/{document_id}/versions",
    response_model=list[VersionSummary],
    summary="문서 버전 목록 조회",
)
async def list_versions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[VersionSummary]:
    await _get_document_or_404(document_id, db)
    versions = await document_service.get_versions(db, document_id)
    return [VersionSummary.model_validate(v) for v in versions]
