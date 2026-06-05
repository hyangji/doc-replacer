from datetime import datetime

from pydantic import BaseModel, Field


# --- Document ---


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VersionSummary(BaseModel):
    id: int
    version_number: int
    changes_summary: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    content_text: str | None = None
    created_at: datetime
    updated_at: datetime
    versions: list[VersionSummary] = []

    model_config = {"from_attributes": True}


# --- Replacement (Excel-based) ---


class ReplacementPair(BaseModel):
    field_name: str
    old_value: str
    new_value: str


class ReplacementRequest(BaseModel):
    replacements: list[ReplacementPair] = Field(..., min_length=1)


class ReplacementResponse(BaseModel):
    document_id: int
    replaced_count: int
    version_number: int


# --- Search / Replace ---


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    case_sensitive: bool = False
    regex: bool = False


class SearchMatch(BaseModel):
    index: int = 0
    line: int = 0
    column: int = 0
    match: str = ""
    context: str = ""
    position: int = 0


class SearchResult(BaseModel):
    document_id: int
    query: str
    matches: list[SearchMatch] = []
    total_count: int = 0


class ReplaceTextRequest(BaseModel):
    search: str = Field(..., min_length=1)
    replace: str
    case_sensitive: bool = False
    regex: bool = False


class ReplaceTextResponse(BaseModel):
    document_id: int
    replaced_count: int
    version_number: int


# --- Diff ---


class DiffResponse(BaseModel):
    document_id: int
    original_text: str
    modified_text: str
    version_number: int
    unified_diff: str = ""
    stats: dict = {}


# --- Excel ---


class ExcelPreviewRow(BaseModel):
    field_name: str
    old_value: str
    new_value: str


class ExcelPreviewResponse(BaseModel):
    headers: list[str] = []
    rows: list[list[str]] = []
    total_rows: int = 0
    replacements: list[ExcelPreviewRow] = []


# --- Comparison Table (대비표 엑셀 기반 교체) ---


class ComparisonChangeItem(BaseModel):
    """대비표 엑셀에서 추출된 단일 교체쌍."""

    sheet: str
    field_name: str
    old_value: str
    new_value: str
    match_count: int = 0


class ComparisonSheetResult(BaseModel):
    """시트 단위 교체쌍 묶음."""

    name: str
    changes: list[ComparisonChangeItem] = []


class ComparisonSectionInfo(BaseModel):
    """대비표 시트 내 하위 구간(표) 단위 파싱 요약.

    8.다 시트처럼 한 시트에 여러 하위표가 있는 경우 각 표가 별도 항목으로
    보고된다. 그 외 시트는 시트 전체가 1개 구간이다.
    """

    sheet: str
    label: str
    extracted_count: int = 0
    # 'parsed'  : 교체쌍 추출 성공(>0)
    # 'empty'   : 데이터는 있으나 추출 0건(변경 없음/확인 필요)
    # 'skipped' : 면적 없는 세부 조서 등 의도적으로 건너뜀
    status: str = "parsed"


class ComparisonPreviewResponse(BaseModel):
    """대비표 미리보기 응답 — 적용 전 사용자 확인용."""

    sheets: list[ComparisonSheetResult] = []
    total_changes: int = 0
    total_matches: int = 0
    unmatched_count: int = 0
    sections: list[ComparisonSectionInfo] = []


# --- HTML 렌더링 (표 보존) ---


class DocumentHtmlResponse(BaseModel):
    """HWP/HWPX를 표 보존 HTML로 렌더한 응답 (편집/Diff 화면용)."""

    html: str


class DocumentCompareHtmlResponse(BaseModel):
    """원본·수정본을 비교해 바뀐 셀/단어를 hwp-changed 클래스로 표시한 HTML 쌍.

    프론트는 original_html / modified_html을 각각 컨테이너에 렌더하고,
    컨테이너별로 .hwp-changed 색을 달리해 원본(삭제)/수정본(추가)을 구분한다.
    """

    original_html: str
    modified_html: str


# --- Convert ---


class ConvertRequest(BaseModel):
    target_format: str = Field(..., pattern="^(docx|pdf)$")


class ConvertResponse(BaseModel):
    document_id: int
    download_url: str
    target_format: str
