// TypeScript interfaces matching backend Pydantic schemas (backend/app/schemas/document.py)

export interface DocumentUploadResponse {
  id: number;
  filename: string;
  original_filename: string;
  file_type: string;
  created_at: string;
}

export interface DocumentListItem {
  id: number;
  filename: string;
  original_filename: string;
  file_type: string;
  created_at: string;
  updated_at: string;
}

export interface VersionSummary {
  id: number;
  version_number: number;
  changes_summary: string | null;
  created_at: string;
}

export interface DocumentDetail {
  id: number;
  filename: string;
  original_filename: string;
  file_type: string;
  file_path: string;
  content_text: string | null;
  created_at: string;
  updated_at: string;
  versions: VersionSummary[];
}

export interface ReplacementPair {
  field_name: string;
  old_value: string;
  new_value: string;
}

export interface ReplacementRequest {
  replacements: ReplacementPair[];
}

export interface ReplacementResponse {
  document_id: number;
  replaced_count: number;
  version_number: number;
}

export interface SearchOptions {
  case_sensitive?: boolean;
  regex?: boolean;
}

export interface SearchMatch {
  text: string;
  position: number;
  context: string;
}

export interface SearchResult {
  document_id: number;
  query: string;
  matches: SearchMatch[];
  total_count: number;
}

export interface ReplaceTextRequest {
  search: string;
  replace: string;
  case_sensitive?: boolean;
  regex?: boolean;
}

export interface ReplaceTextResponse {
  document_id: number;
  replaced_count: number;
  version_number: number;
}

export interface DiffResponse {
  document_id: number;
  original_text: string;
  modified_text: string;
  version_number: number;
}

export interface ConvertRequest {
  target_format: 'docx' | 'pdf';
}

export interface ConvertResponse {
  document_id: number;
  download_url: string;
  target_format: string;
}
