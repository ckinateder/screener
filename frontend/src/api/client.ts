// Typed wrappers around the FastAPI backend (kaching/api.py).

export type Tf = "D" | "W";

/** Chart pane as the API numbers it (1-based). */
export type ApiPane = 1 | 2;

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Point {
  time: string;
  value: number;
}

export interface ChartData {
  symbol: string;
  name: string | null;
  exchange: string | null;
  tf: Tf;
  bars: Bar[];
  /** Keyed by indicator id; Keltner parts are "<id>:upper" | ":mid" | ":lower". */
  indicators: Record<string, Point[]>;
  /** Support zones keyed by "sr" indicator id, nearest below price first. */
  zones: Record<string, Zone[]>;
  healed: boolean;
  stale: boolean;
}

export interface Zone {
  low: number;
  high: number;
  touches: number;
  /** First / last touch (ISO date). */
  first: string;
  last: string;
}

export interface IndicatorSetting {
  id: string;
  kind: "ema" | "sma" | "kc" | "sr";
  tf: Tf;
  color: string;
  width: number;
  visible: boolean;
  length?: number;
  ema_length?: number;
  atr_length?: number;
  multiplier?: number;
  // Support zones ("sr")
  pivot?: number;
  tolerance?: number;
  lookback_years?: number;
  max_zones?: number;
  min_touches?: number;
}

export interface SearchResult {
  symbol: string;
  name: string | null;
  exchange: string | null;
  type: string;
  stored: boolean;
}

export interface ChecklistScore {
  passed: number;
  /** Checks that could be evaluated (e.g. volume is n/a for mutual funds). */
  applicable: number;
  all_pass: boolean;
}

export interface ChecklistItem {
  id: string;
  label: string;
  value: string;
  threshold: string;
  /** null = not applicable (too little history, no volume data). */
  passed: boolean | null;
}

/** Sector ETF for check #14: the user's override, else suggested from Yahoo's industry/sector. */
export interface SectorEtf {
  etf: string;
  source: "override" | "industry" | "sector";
  /** What the app would suggest without an override (null if it has no suggestion). */
  suggested: string | null;
}

/** The Chart Checklist from strategy-rules.md, measured (kaching/analysis/checklist.py). */
export interface Checklist extends ChecklistScore {
  symbol: string;
  as_of: string | null;
  checks: ChecklistItem[];
  /** null for ETFs/funds and unclassified symbols. */
  sector_etf: SectorEtf | null;
}

export interface WatchlistRow {
  symbol: string;
  name: string | null;
  last: number | null;
  change: number | null;
  change_pct: number | null;
  checklist: ChecklistScore | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** fetch + FastAPI error handling; callers decode the body (JSON or text). */
async function send(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      // FastAPI: {detail: string} for HTTPException, {detail: [{loc, msg}]} for validation errors.
      const first = body.detail?.[0];
      detail =
        typeof body.detail === "string" ? body.detail : first ? `${first.loc?.at(-1) ?? "input"}: ${first.msg}` : detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json();
}

async function requestText(path: string): Promise<string> {
  return (await send(path)).text();
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  /** `pane` (1 or 2) selects which chart's indicator settings are applied. */
  chart: (symbol: string, tf: Tf, pane: ApiPane, refresh = false) =>
    request<ChartData>(
      `/api/chart/${encodeURIComponent(symbol)}?tf=${tf}&pane=${pane}${refresh ? "&refresh=1" : ""}`,
    ),
  search: (q: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  settings: (pane: ApiPane) => request<IndicatorSetting[]>(`/api/settings/indicators?pane=${pane}`),
  saveSettings: (pane: ApiPane, settings: IndicatorSetting[]) =>
    request<IndicatorSetting[]>(`/api/settings/indicators?pane=${pane}`, json("PUT", settings)),
  resetSettings: (pane: ApiPane) =>
    request<IndicatorSetting[]>(`/api/settings/indicators?pane=${pane}`, { method: "DELETE" }),
  /** Throttled server-side, so this is cheap to call on load. */
  refreshWatchlist: (force = false) =>
    request<WatchlistRow[]>(`/api/watchlist/refresh${force ? "?force=true" : ""}`, { method: "POST" }),
  setWatchlist: (symbols: string[]) => request<WatchlistRow[]>("/api/watchlist", json("PUT", { symbols })),
  checklist: (symbol: string) => request<Checklist>(`/api/checklist/${encodeURIComponent(symbol)}`),
  /** Override the sector ETF for check #14; null resets to the suggestion. */
  setSectorEtf: (symbol: string, etf: string | null) =>
    request<{ symbol: string; sector_etf: string | null }>(
      `/api/symbols/${encodeURIComponent(symbol)}/sector-etf`,
      json("PUT", { etf }),
    ),
  /** strategy-rules.md as markdown, read live from disk by the backend. */
  strategyRules: () => requestText("/api/strategy-rules"),
};
