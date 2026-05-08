import axios from 'axios';
import { message } from 'antd';
import type {
  DocumentUploadResponse,
  DocumentListItem,
  DocumentDetail,
  DiffResponse,
  SearchOptions,
  SearchResult,
  ReplaceTextResponse,
  ConvertResponse,
  VersionSummary,
} from '@/types/document';
import type { LawSearchResponse, LawVerifyResult, LawDetailResponse } from '@/types/law';
import type { SpellCheckResponse, LegalTermCheckResponse } from '@/types/spellcheck';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/api`
    : '/api',
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const msg =
      error.response?.data?.detail ?? error.message ?? '요청 처리 중 오류가 발생했습니다.';
    message.error(msg);
    return Promise.reject(error);
  },
);

// --- Documents ---

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<DocumentUploadResponse>('/documents/upload', formData);
  return data;
}

export async function getDocuments(): Promise<DocumentListItem[]> {
  const { data } = await api.get<DocumentListItem[]>('/documents/');
  return data;
}

export async function getDocument(id: number): Promise<DocumentDetail> {
  const { data } = await api.get<DocumentDetail>(`/documents/${id}`);
  return data;
}

export async function replaceWithExcel(id: number, file: File): Promise<DiffResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<DiffResponse>(`/documents/${id}/excel-upload`, formData);
  return data;
}

export async function searchDocument(
  id: number,
  query: string,
  options: SearchOptions = {},
): Promise<SearchResult> {
  const { data } = await api.post<SearchResult>(`/documents/${id}/search`, {
    query,
    case_sensitive: options.case_sensitive ?? false,
    regex: options.regex ?? false,
  });
  return data;
}

export async function replaceText(
  id: number,
  target: string,
  replacement: string,
  replaceAll: boolean,
): Promise<ReplaceTextResponse> {
  const { data } = await api.post<ReplaceTextResponse>(`/documents/${id}/replace-text`, {
    search: target,
    replace: replacement,
    replace_all: replaceAll,
  });
  return data;
}

export async function getDiff(id: number): Promise<DiffResponse> {
  const { data } = await api.get<DiffResponse>(`/documents/${id}/diff`);
  return data;
}

export async function revertDocument(id: number, version: number): Promise<DocumentDetail> {
  const { data } = await api.post<DocumentDetail>(`/documents/${id}/revert`, null, {
    params: { version },
  });
  return data;
}

export async function saveDocument(id: number, content: string): Promise<DocumentDetail> {
  const { data } = await api.post<DocumentDetail>(`/documents/${id}/save`, { content });
  return data;
}

export async function convertDocument(id: number, format: 'docx' | 'pdf'): Promise<Blob> {
  const { data } = await api.post<ConvertResponse>(`/documents/${id}/convert`, {
    target_format: format,
  });
  const response = await api.get(data.download_url, { responseType: 'blob' });
  return response.data as Blob;
}

export async function getVersions(id: number): Promise<VersionSummary[]> {
  const { data } = await api.get<VersionSummary[]>(`/documents/${id}/versions`);
  return data;
}

export async function deleteDocument(id: number): Promise<void> {
  await api.delete(`/documents/${id}`);
}

// --- Law ---

export async function searchLaw(query: string, searchType: string = 'law'): Promise<LawSearchResponse> {
  const { data } = await api.get<LawSearchResponse>('/law/search', {
    params: { query, search_type: searchType },
  });
  return data;
}

export async function verifyLaw(lawName: string, articleNumber?: string): Promise<LawVerifyResult> {
  const { data } = await api.post<LawVerifyResult>('/law/verify', {
    law_name: lawName,
    article_number: articleNumber ?? null,
  });
  return data;
}

export async function getLawDetail(lawId: string): Promise<LawDetailResponse> {
  const { data } = await api.get<LawDetailResponse>(`/law/${lawId}`);
  return data;
}

// --- Spell Check ---

export async function checkSpelling(text: string): Promise<SpellCheckResponse> {
  const { data } = await api.post<SpellCheckResponse>('/spellcheck', { text });
  return data;
}

export async function checkLegalTerms(text: string): Promise<LegalTermCheckResponse> {
  const { data } = await api.post<LegalTermCheckResponse>('/spellcheck/legal-terms', { text });
  return data;
}

export default api;
