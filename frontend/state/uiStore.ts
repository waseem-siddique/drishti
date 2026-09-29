// UI state only. Server state belongs to TanStack Query.
// Persisting this is what makes folding, rotating or refreshing non-destructive.
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type WorkFilters = {
  search: string;
  state: string;
  district: string;
  category: string;
  agency: string;
  risk_band: string;
  priority: string;
  status: string;
};

export const emptyFilters: WorkFilters = {
  search: '', state: '', district: '', category: '', agency: '', risk_band: '', priority: '', status: '',
};

type UiState = {
  filters: WorkFilters;
  page: number;
  pageSize: number;
  sort: string;
  direction: 'asc' | 'desc';
  hiddenColumns: string[];
  selectedCaseRef: string | null;
  caseStatusFilter: string;
  expanded: Record<string, boolean>;
  drafts: Record<string, string>;
  sidebarOpen: boolean;
  setFilter: (key: keyof WorkFilters, value: string) => void;
  resetFilters: () => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  setSort: (sort: string) => void;
  toggleColumn: (column: string) => void;
  setSelectedCaseRef: (ref: string | null) => void;
  setCaseStatusFilter: (value: string) => void;
  toggleExpanded: (key: string) => void;
  setDraft: (key: string, value: string) => void;
  clearDraft: (key: string) => void;
  setSidebarOpen: (open: boolean) => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      filters: emptyFilters,
      page: 1,
      pageSize: 25,
      sort: 'priority_index',
      direction: 'desc',
      hiddenColumns: [],
      selectedCaseRef: null,
      caseStatusFilter: '',
      expanded: {},
      drafts: {},
      sidebarOpen: false,
      setFilter: (key, value) => set((s) => ({ filters: { ...s.filters, [key]: value }, page: 1 })),
      resetFilters: () => set({ filters: emptyFilters, page: 1 }),
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      setSort: (sort) =>
        set((s) => (s.sort === sort ? { direction: s.direction === 'desc' ? 'asc' : 'desc' } : { sort, direction: 'desc' })),
      toggleColumn: (column) =>
        set((s) => ({
          hiddenColumns: s.hiddenColumns.includes(column)
            ? s.hiddenColumns.filter((item) => item !== column)
            : [...s.hiddenColumns, column],
        })),
      setSelectedCaseRef: (selectedCaseRef) => set({ selectedCaseRef }),
      setCaseStatusFilter: (caseStatusFilter) => set({ caseStatusFilter }),
      toggleExpanded: (key) => set((s) => ({ expanded: { ...s.expanded, [key]: !s.expanded[key] } })),
      setDraft: (key, value) => set((s) => ({ drafts: { ...s.drafts, [key]: value } })),
      clearDraft: (key) =>
        set((s) => {
          const drafts = { ...s.drafts };
          delete drafts[key];
          return { drafts };
        }),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
    }),
    { name: 'drishti.ui' },
  ),
);
