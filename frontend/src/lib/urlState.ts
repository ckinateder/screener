import type { Tf } from "../api/client";

export interface UrlState {
  symbol?: string;
  tf?: Tf;
}

export function readUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
  const symbol = params.get("symbol")?.trim().toUpperCase();
  const tf = params.get("tf")?.toUpperCase();
  return {
    ...(symbol ? { symbol } : {}),
    ...(tf === "D" || tf === "W" ? { tf } : {}),
  };
}

export function buildUrlSearch(state: Required<UrlState>): string {
  return `?${new URLSearchParams({ symbol: state.symbol, tf: state.tf })}`;
}
