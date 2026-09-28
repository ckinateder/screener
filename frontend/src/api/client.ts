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
  healed: boolean;
  stale: boolean;
}

export interface IndicatorSetting {
  id: string;
  kind: "ema" | "kc";
  tf: Tf;
  color: string;
  width: number;
  visible: boolean;
  length?: number;
  ema_length?: number;
  atr_length?: number;
  multiplier?: number;
}

export interface SearchResult {
  symbol: string;
  name: string | null;
  exchange: string | null;
  type: string;
  stored: boolean;
}

export interface WatchlistRow {
  symbol: string;
  name: string | null;
  last: number | null;
  change: number | null;
  change_pct: number | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  return res.json();
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
};
