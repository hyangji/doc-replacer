// TypeScript interfaces matching backend law schemas (backend/app/routers/law.py)

export interface LawSearchItem {
  law_id: string;
  title: string;
  content_snippet: string;
}

export interface LawSearchResponse {
  query: string;
  results: LawSearchItem[];
  total_count: number;
}

export interface LawVerifyRequest {
  text: string;
  law_id?: string | null;
}

export interface LawVerifyResult {
  is_valid: boolean;
  details: string | null;
  suggestions: string[];
}
