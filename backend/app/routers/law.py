from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services.law_service import LawApiError, LawService

router = APIRouter(prefix="/api/law", tags=["law"])

law_service = LawService()


# --- Schemas ---


class LawSearchItem(BaseModel):
    law_id: str
    law_name: str
    law_type: str = ""
    proclamation_date: str = ""
    enforcement_date: str = ""


class LawSearchResponse(BaseModel):
    query: str
    results: list[LawSearchItem] = []
    total_count: int = 0


class LawDetailArticle(BaseModel):
    number: str
    title: str = ""
    content: str = ""


class LawDetailResponse(BaseModel):
    law_name: str
    law_id: str
    proclamation_date: str = ""
    articles: list[LawDetailArticle] = []


class LawVerifyRequest(BaseModel):
    law_name: str
    article_number: str | None = None


class LawVerifyResult(BaseModel):
    exists: bool
    correct_name: str = ""
    is_current: bool = False
    last_amended: str = ""
    article_exists: bool | None = None


# --- Endpoints ---


@router.get(
    "/search",
    response_model=LawSearchResponse,
    summary="법령 검색",
)
async def search_law(
    query: str = Query(..., min_length=1),
    search_type: str = Query("law", pattern="^(law|jo|key)$"),
    page: int = Query(1, ge=1),
    display: int = Query(20, ge=1, le=100),
) -> LawSearchResponse:
    try:
        results = await law_service.search_law(query, search_type, page, display)
    except LawApiError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    return LawSearchResponse(
        query=query,
        results=[LawSearchItem(**r) for r in results],
        total_count=len(results),
    )


@router.get(
    "/{law_id}",
    response_model=LawDetailResponse,
    summary="법령 상세 조회",
)
async def get_law_detail(
    law_id: str,
) -> LawDetailResponse:
    try:
        detail = await law_service.get_law_detail(law_id)
    except LawApiError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    return LawDetailResponse(**detail)


@router.post(
    "/verify",
    response_model=LawVerifyResult,
    summary="법률 인용 검증",
)
async def verify_law(
    body: LawVerifyRequest,
) -> LawVerifyResult:
    try:
        result = await law_service.verify_law_reference(
            body.law_name, body.article_number
        )
    except LawApiError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    return LawVerifyResult(**result)
