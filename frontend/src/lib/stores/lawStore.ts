import { create } from 'zustand';
import type { LawSearchItem, LawSearchResponse, LawVerifyResult } from '@/types/law';
import * as api from '@/lib/api';

interface LawState {
  searchResults: LawSearchItem[];
  totalCount: number;
  selectedLaw: LawSearchItem | null;
  verifyResult: LawVerifyResult | null;
  isLoading: boolean;
  error: string | null;

  searchLaw: (query: string) => Promise<void>;
  selectLaw: (item: LawSearchItem | null) => void;
  verifyLaw: (text: string, lawId?: string) => Promise<void>;
  clearError: () => void;
  clearResults: () => void;
}

export const useLawStore = create<LawState>((set) => ({
  searchResults: [],
  totalCount: 0,
  selectedLaw: null,
  verifyResult: null,
  isLoading: false,
  error: null,

  searchLaw: async (query: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.searchLaw(query);
      set({
        searchResults: data.results,
        totalCount: data.total_count,
        selectedLaw: data.results.length > 0 ? data.results[0] : null,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '법률 검색에 실패했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  selectLaw: (item) => set({ selectedLaw: item }),

  verifyLaw: async (text: string, lawId?: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.verifyLaw(text, lawId);
      set({ verifyResult: data });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '법률 검증에 실패했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  clearError: () => set({ error: null }),
  clearResults: () => set({ searchResults: [], totalCount: 0, selectedLaw: null, verifyResult: null }),
}));
