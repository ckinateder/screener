import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type IndicatorSetting, type Tf } from "./client";
import { paramsChanged } from "../lib/series";

const keys = {
  chart: (symbol: string, tf: Tf) => ["chart", symbol, tf] as const,
  search: (q: string) => ["search", q] as const,
  settings: ["settings"] as const,
  watchlist: ["watchlist"] as const,
};

export function useChart(symbol: string | null, tf: Tf) {
  return useQuery({
    queryKey: keys.chart(symbol ?? "", tf),
    queryFn: () => api.chart(symbol!, tf),
    enabled: !!symbol,
    placeholderData: keepPreviousData, // keep the old chart on screen while the next one loads
    staleTime: 60_000,
    retry: false,
  });
}

/** Forces an incremental fetch from Yahoo for the current chart, bypassing the server throttle. */
export function useRefreshChart(symbol: string | null, tf: Tf) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.chart(symbol!, tf, true),
    onSuccess: (data) => {
      qc.setQueryData(keys.chart(data.symbol, tf), data);
      qc.invalidateQueries({ queryKey: ["chart", data.symbol] }); // other timeframe
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

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.settings, staleTime: Infinity });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.saveSettings,
    // Optimistic, so the legend eye toggle feels instant.
    onMutate: async (next) => {
      const prev = qc.getQueryData<IndicatorSetting[]>(keys.settings);
      qc.setQueryData(keys.settings, next);
      return { prev };
    },
    onError: (_err, _next, ctx) => qc.setQueryData(keys.settings, ctx?.prev),
    onSuccess: (saved, _next, ctx) => {
      qc.setQueryData(keys.settings, saved);
      // Colour/width/visibility are applied client-side; only parameter changes need recomputing.
      if (!ctx?.prev || paramsChanged(ctx.prev, saved)) qc.invalidateQueries({ queryKey: ["chart"] });
    },
  });
}

export function useResetSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.resetSettings,
    onSuccess: (saved) => {
      qc.setQueryData(keys.settings, saved);
      qc.invalidateQueries({ queryKey: ["chart"] });
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
