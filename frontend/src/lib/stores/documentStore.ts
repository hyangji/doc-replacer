import { create } from 'zustand';
import type { DocumentDetail, DocumentListItem, DiffResponse, SearchResult } from '@/types/document';
import * as api from '@/lib/api';

interface DocumentState {
  currentDocument: DocumentDetail | null;
  documents: DocumentListItem[];
  isLoading: boolean;
  error: string | null;
  diffData: DiffResponse | null;
  searchResults: SearchResult | null;

  fetchDocuments: () => Promise<void>;
  fetchDocument: (id: number) => Promise<void>;
  uploadDocument: (file: File) => Promise<number>;
  saveDocument: (id: number, content: string) => Promise<void>;
  revertDocument: (id: number, version: number) => Promise<void>;
  replaceWithExcel: (id: number, file: File) => Promise<void>;
  deleteDocument: (id: number) => Promise<void>;
  setDiffData: (data: DiffResponse | null) => void;
  setSearchResults: (data: SearchResult | null) => void;
  clearError: () => void;
}

export const useDocumentStore = create<DocumentState>((set, get) => ({
  currentDocument: null,
  documents: [],
  isLoading: false,
  error: null,
  diffData: null,
  searchResults: null,

  fetchDocuments: async () => {
    set({ isLoading: true, error: null });
    try {
      const documents = await api.getDocuments();
      set({ documents });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '문서 목록을 불러오지 못했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchDocument: async (id: number) => {
    set({ isLoading: true, error: null });
    try {
      const doc = await api.getDocument(id);
      set({ currentDocument: doc });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '문서를 불러오지 못했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  uploadDocument: async (file: File) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.uploadDocument(file);
      // Refresh the document list
      const documents = await api.getDocuments();
      set({ documents });
      return res.id;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '업로드에 실패했습니다.';
      set({ error: msg });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  saveDocument: async (id: number, content: string) => {
    set({ isLoading: true, error: null });
    try {
      const doc = await api.saveDocument(id, content);
      set({ currentDocument: doc });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '저장에 실패했습니다.';
      set({ error: msg });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  revertDocument: async (id: number, version: number) => {
    set({ isLoading: true, error: null });
    try {
      const doc = await api.revertDocument(id, version);
      set({ currentDocument: doc, diffData: null });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '되돌리기에 실패했습니다.';
      set({ error: msg });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  replaceWithExcel: async (id: number, file: File) => {
    set({ isLoading: true, error: null });
    try {
      const diff = await api.replaceWithExcel(id, file);
      set({ diffData: diff });
      // Refresh document to get updated content
      const doc = await api.getDocument(id);
      set({ currentDocument: doc });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '엑셀 일괄 교체에 실패했습니다.';
      set({ error: msg });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  deleteDocument: async (id: number) => {
    set({ isLoading: true, error: null });
    try {
      await api.deleteDocument(id);
      const { documents } = get();
      set({ documents: documents.filter((d) => d.id !== id) });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '삭제에 실패했습니다.';
      set({ error: msg });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  setDiffData: (data) => set({ diffData: data }),
  setSearchResults: (data) => set({ searchResults: data }),
  clearError: () => set({ error: null }),
}));
