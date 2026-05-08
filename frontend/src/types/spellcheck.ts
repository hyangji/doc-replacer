export interface SpellError {
  original: string;
  corrected: string;
  position: number;
  type: 'spelling' | 'spacing' | 'grammar';
}

export interface SpellCheckResponse {
  errors: SpellError[];
  total_errors: number;
}

export interface LegalTermError {
  found: string;
  suggested: string;
  position: number;
}

export interface LegalTermCheckResponse {
  errors: LegalTermError[];
  total_errors: number;
}
