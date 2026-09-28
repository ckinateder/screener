import { create } from "zustand";
import type { Tf } from "./api/client";
import { readUrlState, type Layout, type UrlState } from "./lib/urlState";

export type SearchMode = "open" | "add";
export type PaneIndex = 0 | 1;

export interface Pane {
  /** null until resolved from the URL, the watchlist, or the SPY fallback. */
  symbol: string | null;
  tf: Tf;
}

interface UiState {
  panes: [Pane, Pane];
  /** Pane that the top bar, symbol search and watchlist act on. */
  active: PaneIndex;
  layout: Layout;
  /** Scroll/zoom one chart -> the other follows to the same dates. */
  syncRange: boolean;
  /** Stop scrolling past the latest bar (both charts). */
  lockRightEdge: boolean;
  search: { open: boolean; mode: SearchMode; initial: string };
  /** Pane whose indicator settings dialog is open, or null. */
  settingsPane: PaneIndex | null;
  watchlistOpen: boolean;
  /** Sets the active pane's symbol. */
  setSymbol: (symbol: string) => void;
  setPaneSymbol: (pane: PaneIndex, symbol: string) => void;
  /** Sets the active pane's timeframe. */
  setTf: (tf: Tf) => void;
  setActive: (pane: PaneIndex) => void;
  setLayout: (layout: Layout) => void;
  toggleSyncRange: () => void;
  toggleLockRightEdge: () => void;
  openSearch: (mode: SearchMode, initial?: string) => void;
  closeSearch: () => void;
  openSettings: (pane: PaneIndex) => void;
  closeSettings: () => void;
  toggleWatchlist: () => void;
}

export const STORAGE_KEY = "kaching:view";

/** URL wins; a bare URL restores the last saved view. */
function initialView(): UrlState {
  const fromUrl = readUrlState(window.location.search);
  if (Object.keys(fromUrl).length) return fromUrl;
  try {
    return readUrlState(localStorage.getItem(STORAGE_KEY) ?? "");
  } catch {
    return {};
  }
}

const view = initialView();

const otherTf = (tf: Tf): Tf => (tf === "D" ? "W" : "D");

const withPane = (panes: [Pane, Pane], i: PaneIndex, patch: Partial<Pane>): [Pane, Pane] => {
  const next: [Pane, Pane] = [...panes];
  next[i] = { ...panes[i], ...patch };
  return next;
};

export const useUi = create<UiState>((set) => ({
  panes: [
    { symbol: view.symbol ?? null, tf: view.tf ?? "D" },
    { symbol: view.symbol2 ?? null, tf: view.tf2 ?? otherTf(view.tf ?? "D") },
  ],
  active: 0,
  layout: view.layout ?? "single",
  syncRange: view.sync ?? true,
  lockRightEdge: view.lock ?? false,
  search: { open: false, mode: "open", initial: "" },
  settingsPane: null,
  watchlistOpen: true,
  setSymbol: (symbol) => set((s) => ({ panes: withPane(s.panes, s.active, { symbol: symbol.toUpperCase() }) })),
  setPaneSymbol: (i, symbol) => set((s) => ({ panes: withPane(s.panes, i, { symbol: symbol.toUpperCase() }) })),
  setTf: (tf) => set((s) => ({ panes: withPane(s.panes, s.active, { tf }) })),
  setActive: (active) => set({ active }),
  setLayout: (layout) =>
    set((s) => {
      if (layout === "single") return { layout, active: 0 };
      // First split: open the same symbol on the other timeframe (the D + W workflow).
      const [first, second] = s.panes;
      const panes = second.symbol ? s.panes : withPane(s.panes, 1, { symbol: first.symbol, tf: otherTf(first.tf) });
      return { layout, panes };
    }),
  toggleSyncRange: () => set((s) => ({ syncRange: !s.syncRange })),
  toggleLockRightEdge: () => set((s) => ({ lockRightEdge: !s.lockRightEdge })),
  openSearch: (mode, initial = "") => set({ search: { open: true, mode, initial } }),
  closeSearch: () => set((s) => ({ search: { ...s.search, open: false } })),
  openSettings: (settingsPane) => set({ settingsPane }),
  closeSettings: () => set({ settingsPane: null }),
  toggleWatchlist: () => set((s) => ({ watchlistOpen: !s.watchlistOpen })),
}));

export const useActivePane = () => useUi((s) => s.panes[s.active]);
