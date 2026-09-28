import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ApiPane, type IndicatorSetting, type Tf } from "./client";
import { paramsChanged } from "../lib/series";
import type { PaneIndex } from "../store";

// Each chart pane has its own indicator settings, so chart data is cached per pane too.
const toApi = (pane: PaneIndex): ApiPane => (pane + 1) as ApiPane;

const keys = {
  chart: (pane: PaneIndex, symbol: string, tf: Tf) => ["chart", pane, symbol, tf] as const,
  paneCharts: (pane: PaneIndex) => ["chart", pane] as const,
  search: (q: string) => ["search", q] as const,
  settings: (pane: PaneIndex) => ["settings", pane] as const,
  watchlist: ["watchlist"] as const,
};

export function useChart(pane: PaneIndex, symbol: string | null, tf: Tf) {
  return useQuery({
    queryKey: keys.chart(pane, symbol ?? "", tf),
    queryFn: () => api.chart(symbol!, tf, toApi(pane)),
    enabled: !!symbol,
    placeholderData: keepPreviousData, // keep the old chart on screen while the next one loads
    staleTime: 60_000,
    retry: false,
  });
}

/** Forces an incremental fetch from Yahoo for the current chart, bypassing the server throttle. */
export function useRefreshChart(pane: PaneIndex, symbol: string | null, tf: Tf) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.chart(symbol!, tf, toApi(pane), true),
    onSuccess: (data) => {
      qc.setQueryData(keys.chart(pane, data.symbol, tf), data);
      // New bars: every cached chart of this symbol (other timeframe / other pane) is stale.
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "chart" && q.queryKey[2] === data.symbol });
      qc.invalidateQueries({ queryKey: keys.watchlist });
    },
  });
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: keys.search(q),
    queryFn: () => api.search(q),
    enabled: q.length > 0,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useSettings(pane: PaneIndex) {
  return useQuery({ queryKey: keys.settings(pane), queryFn: () => api.settings(toApi(pane)), staleTime: Infinity });
}

export function useSaveSettings(pane: PaneIndex) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (settings: IndicatorSetting[]) => api.saveSettings(toApi(pane), settings),
    // Optimistic, so the legend eye toggle feels instant.
    onMutate: async (next) => {
      const prev = qc.getQueryData<IndicatorSetting[]>(keys.settings(pane));
      qc.setQueryData(keys.settings(pane), next);
      return { prev };
    },
    onError: (_err, _next, ctx) => qc.setQueryData(keys.settings(pane), ctx?.prev),
    onSuccess: (saved, _next, ctx) => {
      qc.setQueryData(keys.settings(pane), saved);
      // Colour/width/visibility are applied client-side; only parameter changes need recomputing.
      if (!ctx?.prev || paramsChanged(ctx.prev, saved)) qc.invalidateQueries({ queryKey: keys.paneCharts(pane) });
    },
  });
}

export function useResetSettings(pane: PaneIndex) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.resetSettings(toApi(pane)),
    onSuccess: (saved) => {
      qc.setQueryData(keys.settings(pane), saved);
      qc.invalidateQueries({ queryKey: keys.paneCharts(pane) });
    },
  });
}

export function useWatchlist() {
  return useQuery({
    queryKey: keys.watchlist,
    queryFn: () => api.refreshWatchlist(),
    staleTime: 5 * 60_000,
  });
}

export function useSetWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.setWatchlist,
    onSuccess: (rows) => qc.setQueryData(keys.watchlist, rows),
  });
}

export function useForceRefreshWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.refreshWatchlist(true),
    onSuccess: (rows) => {
      qc.setQueryData(keys.watchlist, rows);
      qc.invalidateQueries({ queryKey: ["chart"] });
    },
  });
}
