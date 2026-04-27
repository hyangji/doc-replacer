from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services.spellcheck_service import SpellCheckService

router = APIRouter(prefix="/api/spellcheck", tags=["spellcheck"])

spellcheck_service = SpellCheckService()


# --- Schemas ---


class SpellCheckRequest(BaseModel):
    text: str = Field(..., min_length=1)


class SpellError(BaseModel):
    original: str
    corrected: str
    position: int
    type: str  # "spelling" | "spacing" | "grammar"


class SpellCheckResponse(BaseModel):
    errors: list[SpellError] = []
    total_errors: int = 0


class LegalTermCheckRequest(BaseModel):
    text: str = Field(..., min_length=1)


class LegalTermError(BaseModel):
    found: str
    suggested: str
    position: int


class LegalTermCheckResponse(BaseModel):
    errors: list[LegalTermError] = []
    total_errors: int = 0


# --- Endpoints ---


@router.post(
    "",
    response_model=SpellCheckResponse,
    summary="맞춤법 검사",
)
async def check_spelling(
    body: SpellCheckRequest,
) -> SpellCheckResponse:
    errors = await spellcheck_service.check_text(body.text)
    return SpellCheckResponse(
        errors=[SpellError(**e) for e in errors],
        total_errors=len(errors),
    )


@router.post(
    "/legal-terms",
    response_model=LegalTermCheckResponse,
    summary="법률 용어 오타 검출",
)
async def check_legal_terms(
    body: LegalTermCheckRequest,
) -> LegalTermCheckResponse:
    errors = await spellcheck_service.check_legal_terms(body.text)
    return LegalTermCheckResponse(
        errors=[LegalTermError(**e) for e in errors],
        total_errors=len(errors),
    )
