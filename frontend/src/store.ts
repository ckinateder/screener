import { create } from "zustand";
import type { Tf } from "./api/client";
import { readUrlState } from "./lib/urlState";

export type SearchMode = "open" | "add";

interface UiState {
  /** null until resolved from the URL, the watchlist, or the SPY fallback. */
  symbol: string | null;
  tf: Tf;
  search: { open: boolean; mode: SearchMode; initial: string };
  settingsOpen: boolean;
  watchlistOpen: boolean;
  setSymbol: (symbol: string) => void;
  setTf: (tf: Tf) => void;
  openSearch: (mode: SearchMode, initial?: string) => void;
  closeSearch: () => void;
  setSettingsOpen: (open: boolean) => void;
  toggleWatchlist: () => void;
}

const fromUrl = readUrlState(window.location.search);

export const useUi = create<UiState>((set) => ({
  symbol: fromUrl.symbol ?? null,
  tf: fromUrl.tf ?? "D",
  search: { open: false, mode: "open", initial: "" },
  settingsOpen: false,
  watchlistOpen: true,
  setSymbol: (symbol) => set({ symbol: symbol.toUpperCase() }),
  setTf: (tf) => set({ tf }),
  openSearch: (mode, initial = "") => set({ search: { open: true, mode, initial } }),
  closeSearch: () => set((s) => ({ search: { ...s.search, open: false } })),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  toggleWatchlist: () => set((s) => ({ watchlistOpen: !s.watchlistOpen })),
}));
