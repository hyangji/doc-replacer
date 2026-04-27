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
    file_path: str
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


# --- Convert ---


class ConvertRequest(BaseModel):
    target_format: str = Field(..., pattern="^(docx|pdf)$")


class ConvertResponse(BaseModel):
    document_id: int
    download_url: str
    target_format: str
