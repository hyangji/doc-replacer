import { create } from 'zustand';
import type { LawSearchItem, LawVerifyResult, LawDetailResponse } from '@/types/law';
import * as api from '@/lib/api';

interface LawState {
  searchResults: LawSearchItem[];
  totalCount: number;
  selectedLaw: LawSearchItem | null;
  lawDetail: LawDetailResponse | null;
  verifyResult: LawVerifyResult | null;
  isLoading: boolean;
  error: string | null;

  searchLaw: (query: string, searchType?: string) => Promise<void>;
  selectLaw: (item: LawSearchItem | null) => void;
  getLawDetail: (lawId: string) => Promise<void>;
  verifyLaw: (lawName: string, articleNumber?: string) => Promise<void>;
  clearError: () => void;
  clearResults: () => void;
}

export const useLawStore = create<LawState>((set) => ({
  searchResults: [],
  totalCount: 0,
  selectedLaw: null,
  lawDetail: null,
  verifyResult: null,
  isLoading: false,
  error: null,

  searchLaw: async (query: string, searchType: string = 'law') => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.searchLaw(query, searchType);
      set({
        searchResults: data.results,
        totalCount: data.total_count,
        selectedLaw: data.results.length > 0 ? data.results[0] : null,
        lawDetail: null,
      });
      if (data.results.length > 0 && data.results[0].law_id) {
        try {
          const detail = await api.getLawDetail(data.results[0].law_id);
          set({ lawDetail: detail });
        } catch {
          // 상세 조회 실패해도 검색 결과 유지
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '법률 검색에 실패했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  selectLaw: (item) => {
    set({ selectedLaw: item, lawDetail: null });
    if (item?.law_id) {
      api.getLawDetail(item.law_id).then(detail => {
        set({ lawDetail: detail });
      }).catch(() => {});
    }
  },

  getLawDetail: async (lawId: string) => {
    try {
      const detail = await api.getLawDetail(lawId);
      set({ lawDetail: detail });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '법령 상세 조회에 실패했습니다.';
      set({ error: msg });
    }
  },

  verifyLaw: async (lawName: string, articleNumber?: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.verifyLaw(lawName, articleNumber);
      set({ verifyResult: data });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '법률 검증에 실패했습니다.';
      set({ error: msg });
    } finally {
      set({ isLoading: false });
    }
  },

  clearError: () => set({ error: null }),
  clearResults: () => set({ searchResults: [], totalCount: 0, selectedLaw: null, lawDetail: null, verifyResult: null }),
}));
