export interface LawSearchItem {
  law_id: string;
  law_name: string;
  law_type: string;
  proclamation_date: string;
  enforcement_date: string;
}

export interface LawSearchResponse {
  query: string;
  results: LawSearchItem[];
  total_count: number;
}

export interface LawVerifyRequest {
  law_name: string;
  article_number?: string | null;
}

export interface LawVerifyResult {
  exists: boolean;
  correct_name: string;
  is_current: boolean;
  last_amended: string;
  article_exists: boolean | null;
}

export interface LawDetailArticle {
  number: string;
  title: string;
  content: string;
}

export interface LawDetailResponse {
  law_name: string;
  law_id: string;
  proclamation_date: string;
  articles: LawDetailArticle[];
}
