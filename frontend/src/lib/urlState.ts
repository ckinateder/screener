import type { Tf } from "../api/client";

export type Layout = "single" | "columns" | "rows";
const LAYOUTS: Layout[] = ["single", "columns", "rows"];

export interface UrlState {
  symbol?: string;
  tf?: Tf;
  symbol2?: string;
  tf2?: Tf;
  layout?: Layout;
  sync?: boolean;
  /** Stop scrolling past the latest bar. */
  lock?: boolean;
}

const readSymbol = (v: string | null) => v?.trim().toUpperCase() || undefined;
const readTf = (v: string | null): Tf | undefined => {
  const tf = v?.toUpperCase();
  return tf === "D" || tf === "W" ? tf : undefined;
};

/** Parses the app state from a query string; unknown or invalid values are dropped. */
export function readUrlState(search: string): UrlState {
  const p = new URLSearchParams(search);
  const layout = p.get("layout") as Layout | null;
  const sync = p.get("sync");
  const state: UrlState = {
    symbol: readSymbol(p.get("symbol")),
    tf: readTf(p.get("tf")),
    symbol2: readSymbol(p.get("symbol2")),
    tf2: readTf(p.get("tf2")),
    layout: layout && LAYOUTS.includes(layout) ? layout : undefined,
    sync: sync === "1" ? true : sync === "0" ? false : undefined,
    lock: p.get("lock") === "1" ? true : undefined,
  };
  return Object.fromEntries(Object.entries(state).filter(([, v]) => v !== undefined)) as UrlState;
}

export function buildUrlSearch(state: UrlState): string {
  const p = new URLSearchParams();
  if (state.symbol) p.set("symbol", state.symbol);
  if (state.tf) p.set("tf", state.tf);
  // Second-pane params only matter in a split layout; keep single-chart URLs short.
  if (state.layout && state.layout !== "single") {
    if (state.symbol2) p.set("symbol2", state.symbol2);
    if (state.tf2) p.set("tf2", state.tf2);
    p.set("layout", state.layout);
    if (state.sync !== undefined) p.set("sync", state.sync ? "1" : "0");
  }
  if (state.lock) p.set("lock", "1"); // applies to single and split layouts
  return `?${p}`;
}
