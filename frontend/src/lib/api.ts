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
  ComparisonPreviewResponse,
  ReplacementItem,
  ReplacementResponse,
} from '@/types/document';
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/api`
    : '/_/backend/api',
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

export async function downloadDocument(
  id: number,
  version?: number,
): Promise<{ blob: Blob; filename: string }> {
  const { data, headers } = await api.get(`/documents/${id}/download`, {
    params: version != null ? { version } : undefined,
    responseType: 'blob',
  });

  // Content-Disposition에서 RFC5987 filename* 우선 파싱, 없으면 일반 filename, 그래도 없으면 기본값
  const disposition = (headers['content-disposition'] as string | undefined) ?? '';
  let filename = '문서_수정본.hwp';
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      filename = decodeURIComponent(utf8Match[1].trim());
    } catch {
      filename = utf8Match[1].trim();
    }
  } else {
    const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
    if (plainMatch) {
      filename = plainMatch[1].trim();
    }
  }

  return { blob: data as Blob, filename };
}

export async function getDocumentHtml(id: number, version?: number): Promise<string> {
  const { data } = await api.get<{ html: string }>(`/documents/${id}/html`, {
    params: version != null ? { version } : undefined,
  });
  return data.html;
}

export async function getDocumentCompareHtml(
  id: number,
  base: number,
  target?: number,
): Promise<{ original_html: string; modified_html: string }> {
  const { data } = await api.get<{ original_html: string; modified_html: string }>(
    `/documents/${id}/html/compare`,
    { params: { base, ...(target != null ? { target } : {}) } },
  );
  return data;
}

export async function getVersions(id: number): Promise<VersionSummary[]> {
  const { data } = await api.get<VersionSummary[]>(`/documents/${id}/versions`);
  return data;
}

export async function deleteDocument(id: number): Promise<void> {
  await api.delete(`/documents/${id}`);
}

// --- 대비표 기반 HWP 표 일괄 수정 ---

export async function previewComparison(
  id: number,
  file: File,
): Promise<ComparisonPreviewResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<ComparisonPreviewResponse>(
    `/documents/${id}/replace/comparison/preview`,
    formData,
  );
  return data;
}

export async function applyReplacements(
  id: number,
  replacements: ReplacementItem[],
): Promise<ReplacementResponse> {
  const { data } = await api.post<ReplacementResponse>(`/documents/${id}/replace`, {
    replacements,
  });
  return data;
}

export default api;
