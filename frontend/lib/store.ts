"use client";

import { create } from "zustand";
import type { TraceEvent } from "./api.types";

interface AppState {
  selectedCaseId: string | null;
  editorDraft: Record<string, unknown> | null;
  traceEvents: TraceEvent[];
  setSelectedCase: (id: string | null) => void;
  setEditorDraft: (draft: Record<string, unknown> | null) => void;
  pushTrace: (ev: TraceEvent) => void;
  clearTrace: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedCaseId: null,
  editorDraft: null,
  traceEvents: [],
  setSelectedCase: (selectedCaseId) => set({ selectedCaseId }),
  setEditorDraft: (editorDraft) => set({ editorDraft }),
  pushTrace: (ev) =>
    set((s) => ({ traceEvents: [...s.traceEvents.slice(-499), ev] })),
  clearTrace: () => set({ traceEvents: [] }),
}));
