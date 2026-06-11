import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.document import (
    ComparisonChangeItem,
    ComparisonPreviewResponse,
    ComparisonSectionInfo,
    ComparisonSheetResult,
    ConvertRequest,
    ConvertResponse,
    DiffResponse,
    DocumentCompareHtmlResponse,
    DocumentDetail,
    DocumentHtmlResponse,
    DocumentListItem,
    DocumentUploadResponse,
    ExcelPreviewResponse,
    ReplacementRequest,
    ReplacementResponse,
    ReplaceTextRequest,
    ReplaceTextResponse,
    SaveBlocksRequest,
    SearchRequest,
    SearchResult,
    VersionSummary,
)
from app.services import document_service
from app.services.document_service import DocumentServiceError
from app.services.diff_service import DiffServiceError
from app.services.excel_service import ExcelParseError, ExcelServiceError

router = APIRouter(prefix="/api/documents", tags=["documents"])


class SaveDocumentRequest(BaseModel):
    content: str


async def _get_document_or_404(document_id: int, db: AsyncSession):
    try:
        doc = await document_service.get_document(db, document_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결에 실패했습니다.",
        )
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
    try:
        docs = await document_service.list_documents(db)
        return [DocumentListItem.model_validate(d) for d in docs]
    except Exception:
        return []


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
    "/{document_id}/excel-upload",
    response_model=ReplacementResponse,
    summary="엑셀 파일 업로드 후 일괄 교체 (별칭)",
)
async def excel_upload_alias(
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ReplacementResponse:
    return await replace_from_excel(document_id, file, db)


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
    "/{document_id}/replace/comparison/preview",
    response_model=ComparisonPreviewResponse,
    summary="대비표 엑셀 미리보기 (기정→변경후 교체쌍 + HWP 매칭 수 확인)",
)
async def preview_comparison_replacement(
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ComparisonPreviewResponse:
    """도시계획 고시문 대비표 엑셀을 업로드하고 교체쌍 및 HWP 매칭 수를 미리 확인한다.

    파일을 수정하지 않는 순수 미리보기 엔드포인트.
    실제 교체는 기존 POST /{document_id}/replace (JSON ReplacementRequest) 로 수행한다.
    """
    doc = await _get_document_or_404(document_id, db)

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="엑셀 파일(.xlsx)만 업로드 가능합니다.",
        )

    content = await file.read()

    # 1. 대비표 파싱 (v2: 교체쌍 + 구간 메타데이터)
    try:
        from app.services.excel_service import parse_comparison_table_excel_v2
        parsed = parse_comparison_table_excel_v2(content)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    items = parsed["items"]
    sections = parsed["sections"]
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "엑셀 대비표에서 유효한 교체쌍을 찾을 수 없습니다. "
                "파일 형식이 도시계획 고시문 대비표(기정/변경후 구조)인지 확인하세요."
            ),
        )

    # 2. 문서 텍스트 추출 (매칭 수 계산용)
    if not doc.file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="문서 파일 데이터가 없습니다.",
        )

    from app.services.hwp_service import HwpService, HwpParseError
    hwp_svc = HwpService()
    ft = doc.file_type.value
    try:
        hwp_text = await hwp_svc.get_text_content(doc.file_data, ft)
    except HwpParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"문서 텍스트 추출 실패: {e}",
        )

    # 3. 각 교체쌍의 HWP 매칭 수 계산 및 시트별 그룹핑
    sheets_map: dict[str, list[ComparisonChangeItem]] = {}
    total_matches = 0
    unmatched_count = 0

    for it in items:
        match_count = hwp_text.count(it["old_value"])
        change_item = ComparisonChangeItem(
            sheet=it["sheet"],
            field_name=it["field_name"],
            old_value=it["old_value"],
            new_value=it["new_value"],
            match_count=match_count,
        )
        sheets_map.setdefault(it["sheet"], []).append(change_item)
        total_matches += match_count
        if match_count == 0:
            unmatched_count += 1

    sheet_results = [
        ComparisonSheetResult(name=sheet_name, changes=changes)
        for sheet_name, changes in sheets_map.items()
    ]

    section_infos = [
        ComparisonSectionInfo(
            sheet=s["sheet"],
            label=s["label"],
            extracted_count=s["extracted_count"],
            status=s["status"],
        )
        for s in sections
    ]

    return ComparisonPreviewResponse(
        sheets=sheet_results,
        total_changes=len(items),
        total_matches=total_matches,
        unmatched_count=unmatched_count,
        sections=section_infos,
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
    "/{document_id}/reset",
    response_model=DocumentDetail,
    summary="원본(v1)으로 초기화",
)
async def reset_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    """문서를 원본(version 1) 상태로 초기화한다.

    대비표 적용·손편집 등으로 누적된 모든 변경을 해제하고, 원본 내용으로
    새 버전을 만들어 latest 로 둔다. 이후 diff(원본 vs 최신)는 '변경 없음'.
    """
    doc = await _get_document_or_404(document_id, db)
    try:
        updated_doc = await document_service.reset_to_original(db, doc)
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DocumentDetail.model_validate(updated_doc)


@router.post(
    "/{document_id}/save",
    response_model=DocumentDetail,
    status_code=status.HTTP_200_OK,
    summary="문서 저장",
)
async def save_document(
    document_id: int,
    body: SaveDocumentRequest,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await _get_document_or_404(document_id, db)
    try:
        updated_doc = await document_service.save_document_content(db, doc, body.content)
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DocumentDetail.model_validate(updated_doc)


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
    "/{document_id}/download",
    summary="수정본 HWP/HWPX 파일 다운로드",
)
async def download_document(
    document_id: int,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """수정본(또는 특정 버전) HWP/HWPX 바이너리를 내려준다.

    - version 지정 시: 해당 DocumentVersion.file_data (없으면 404)
    - version 미지정 시: 최신 버전 file_data, 없으면 document.file_data
    파일명은 원본명 stem + "_수정본" + 확장자 (RFC 5987 인코딩).
    """
    doc = await _get_document_or_404(document_id, db)

    if version is not None:
        target_version = await document_service.get_version_by_number(
            db, document_id, version
        )
        if target_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"버전을 찾을 수 없습니다: {version}",
            )
        file_data = target_version.file_data
    else:
        latest = await document_service.get_latest_version(db, document_id)
        file_data = latest.file_data if latest and latest.file_data else doc.file_data

    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="다운로드할 파일 데이터가 없습니다",
        )

    stem, ext = os.path.splitext(doc.original_filename or f"document_{document_id}")
    if not ext:
        ext = f".{doc.file_type.value}"
    download_name = f"{stem}_수정본{ext}"

    # ASCII fallback (non-ASCII는 _ 로 치환), RFC 5987 filename* 둘 다 제공
    ascii_fallback = download_name.encode("ascii", "replace").decode("ascii").replace("?", "_")
    encoded_name = quote(download_name)
    content_disposition = (
        f"attachment; filename=\"{ascii_fallback}\"; "
        f"filename*=UTF-8''{encoded_name}"
    )

    return Response(
        content=bytes(file_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition},
    )


@router.get(
    "/{document_id}/html",
    response_model=DocumentHtmlResponse,
    summary="표 보존 HTML 렌더링 (편집/Diff 화면용)",
)
async def get_document_html(
    document_id: int,
    version: int | None = None,
    editable: bool = False,
    db: AsyncSession = Depends(get_db),
) -> DocumentHtmlResponse:
    """HWP/HWPX 본문을 표가 <table>로 보존된 HTML 조각으로 렌더해 반환한다.

    - version 지정 시: 해당 DocumentVersion.file_data
    - version 미지정 시: 최신 버전 file_data, 없으면 document.file_data
    - editable=true 시: 편집 영역(표 밖 <p>, 표 셀 <td>)에 data-eid(0..N-1)를 부여.
      이 eid 는 POST /{id}/save-blocks 의 edits[].eid 와 동일하게 매핑된다.
    응답: {"html": "<p data-eid=..>..</p><table>..<td data-eid=..>..</td>..</table>.."}
    """
    doc = await _get_document_or_404(document_id, db)

    if version is not None:
        target_version = await document_service.get_version_by_number(
            db, document_id, version
        )
        if target_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"버전을 찾을 수 없습니다: {version}",
            )
        file_data = target_version.file_data
    else:
        latest = await document_service.get_latest_version(db, document_id)
        file_data = latest.file_data if latest and latest.file_data else doc.file_data

    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="렌더링할 파일 데이터가 없습니다.",
        )

    from app.services.hwp_service import HwpParseError, render_hwp_to_html

    try:
        rendered = render_hwp_to_html(
            bytes(file_data), doc.file_type.value, editable=editable
        )
    except HwpParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"HTML 렌더링 실패: {e}",
        )

    return DocumentHtmlResponse(html=rendered)


@router.post(
    "/{document_id}/save-blocks",
    response_model=DocumentDetail,
    status_code=status.HTTP_200_OK,
    summary="구조 보존 인라인 편집 저장 (data-eid 영역 텍스트)",
)
async def save_document_blocks(
    document_id: int,
    body: SaveBlocksRequest,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    """편집 영역(data-eid)의 새 텍스트만 원본 HWP/HWPX 에 무손실 반영해 저장한다.

    body: {"edits": [{"eid": int, "text": str}, ...]}
      - eid 는 GET /{id}/html?editable=true 응답의 data-eid 와 동일.
      - 표 구조·서식은 변경하지 않고 해당 영역의 텍스트만 교체한다.
    응답: DocumentDetail (새 버전이 versions 에 추가됨).
    """
    doc = await _get_document_or_404(document_id, db)
    try:
        edits = [e.model_dump() for e in body.edits]
        updated_doc = await document_service.save_document_blocks(db, doc, edits)
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DocumentDetail.model_validate(updated_doc)


@router.get(
    "/{document_id}/html/compare",
    response_model=DocumentCompareHtmlResponse,
    summary="원본·수정본 비교 HTML 렌더링 (바뀐 셀/단어 하이라이트)",
)
async def get_document_compare_html(
    document_id: int,
    base: int = 1,
    target: int | None = None,
    editable: bool = False,
    db: AsyncSession = Depends(get_db),
) -> DocumentCompareHtmlResponse:
    """원본(base 버전)과 수정본(target 버전, 없으면 최신)을 비교해

    바뀐 표 셀/문단 단어를 class="hwp-changed"로 강조한 HTML 쌍을 반환한다.
    응답: {"original_html": "...", "modified_html": "..."}

    버전 매핑:
      - DocumentVersion.version_number 로 file_data를 가져온다.
      - base/target 버전이 없으면 404.

    editable=true 면 modified_html 에 data-eid(편집 좌표) 와 변경 영역의
    data-orig(원본 텍스트, 셀별 되돌리기용)를 부여한다.
    이 data-eid 는 POST /{id}/save-blocks 의 edits[].eid 와 동일하게 매핑된다.
    original_html 에도 동일한 data-eid 가 1:1로 부여되어(수정본 셀 클릭 → 원본
    같은 셀 강조용) 정렬되며, 원본은 data-orig/contenteditable 없이 eid 만 갖는다.
    """
    doc = await _get_document_or_404(document_id, db)

    base_version = await document_service.get_version_by_number(db, document_id, base)
    if base_version is None or not base_version.file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"원본 버전을 찾을 수 없습니다: {base}",
        )

    if target is not None:
        target_version = await document_service.get_version_by_number(
            db, document_id, target
        )
    else:
        target_version = await document_service.get_latest_version(db, document_id)

    if target_version is None or not target_version.file_data:
        detail = (
            f"수정본 버전을 찾을 수 없습니다: {target}"
            if target is not None
            else "수정본 버전을 찾을 수 없습니다."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    from app.services.hwp_service import HwpParseError, render_hwp_compare_html

    try:
        result = render_hwp_compare_html(
            bytes(base_version.file_data),
            bytes(target_version.file_data),
            doc.file_type.value,
            editable=editable,
        )
    except HwpParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"비교 HTML 렌더링 실패: {e}",
        )

    return DocumentCompareHtmlResponse(**result)


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


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="문서 삭제",
)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_document_or_404(document_id, db)
    await document_service.delete_document(db, doc)
