import { useEffect, useMemo, useRef } from "react";
import { useChart, useRefreshChart, useWatchlist } from "./api/hooks";
import type { ChartHandle } from "./components/Chart";
import { ChartPane, type PaneSync } from "./components/ChartPane";
import { IndicatorSettings } from "./components/IndicatorSettings";
import { SymbolSearch } from "./components/SymbolSearch";
import { TopBar } from "./components/TopBar";
import { Watchlist } from "./components/Watchlist";
import { buildUrlSearch } from "./lib/urlState";
import { STORAGE_KEY, useActivePane, useUi, type PaneIndex } from "./store";

const FALLBACK_SYMBOL = "SPY";

const GRID = {
  single: "grid-cols-1",
  columns: "grid-cols-2 gap-1",
  rows: "grid-rows-2 gap-1",
} as const;

export default function App() {
  const { panes, active: activeIndex, layout, syncRange, lockRightEdge, setPaneSymbol, search, settingsPane, watchlistOpen } =
    useUi();
  const active = useActivePane();
  const watchlist = useWatchlist();
  const activeChart = useChart(activeIndex, active.symbol, active.tf); // shares the pane's query cache
  const refresh = useRefreshChart(activeIndex, active.symbol, active.tf);

  // No symbol in the URL/saved view: open the first watchlist entry, else SPY.
  useEffect(() => {
    if (panes[0].symbol || watchlist.isLoading) return;
    setPaneSymbol(0, watchlist.data?.[0]?.symbol ?? FALLBACK_SYMBOL);
  }, [panes, watchlist.isLoading, watchlist.data, setPaneSymbol]);

  // Mirror the view into the URL (bookmarkable) and localStorage (restored on a bare URL).
  useEffect(() => {
    const [a, b] = panes;
    if (!a.symbol) return;
    const query = buildUrlSearch({
      symbol: a.symbol, tf: a.tf, symbol2: b.symbol ?? undefined, tf2: b.tf, layout, sync: syncRange, lock: lockRightEdge,
    });
    window.history.replaceState(null, "", query);
    try {
      localStorage.setItem(STORAGE_KEY, query);
    } catch {
      /* storage unavailable (private mode) */
    }
    document.title = `${active.symbol ?? a.symbol} · Kaching`;
  }, [panes, layout, syncRange, lockRightEdge, active.symbol]);

  // Crosshair (always) and X-axis (when enabled) sync between the two charts.
  const handles = useRef<[ChartHandle | null, ChartHandle | null]>([null, null]);
  const syncRangeRef = useRef(syncRange);
  syncRangeRef.current = syncRange;
  // Both price axes get the wider of the two widths, so the plot areas (and dates) line up.
  const scaleWidths = useRef<[number, number]>([0, 0]);
  const appliedScaleWidth = useRef(0);
  const activeRef = useRef(activeIndex);
  activeRef.current = activeIndex;
  /** Snap the inactive chart's X range to the active chart's. */
  const alignToActive = () => {
    if (!syncRangeRef.current) return;
    const source = handles.current[activeRef.current]?.getRange();
    if (source) handles.current[activeRef.current === 0 ? 1 : 0]?.setRange(source);
  };
  const paneSync = useMemo(
    () =>
      ([0, 1] as PaneIndex[]).map((i): PaneSync => {
        const other = () => handles.current[i === 0 ? 1 : 0];
        return {
          onReady: (h) => (handles.current[i] = h),
          onCrosshair: (time) => other()?.showCrosshair(time),
          onRangeChange: (range) => syncRangeRef.current && other()?.setRange(range),
          getInitialRange: () => (syncRangeRef.current ? (other()?.getRange() ?? null) : null),
          onScaleWidth: (px) => {
            scaleWidths.current[i] = px;
            const widest = Math.max(...scaleWidths.current);
            if (!handles.current[1] || widest === appliedScaleWidth.current) return;
            appliedScaleWidth.current = widest;
            handles.current.forEach((h) => h?.setMinScaleWidth(widest));
            // Widening an axis narrows that chart's plot area and shifts its visible range. That
            // happens while the post-load sync guard is still held, so re-align explicitly once
            // the charts have re-laid out.
            requestAnimationFrame(() => requestAnimationFrame(alignToActive));
          },
        };
      }),
    [],
  );
  const split = layout !== "single";
  // Single layout unmounts pane 2; forget its handle and width so pane 1 stops matching it.
  useEffect(() => {
    if (split) return;
    handles.current[1] = null;
    scaleWidths.current = [0, 0];
    appliedScaleWidth.current = 0;
    handles.current[0]?.setMinScaleWidth(0);
  }, [split]);
  // Turning sync on snaps the other chart to the active one.
  useEffect(alignToActive, [syncRange]);

  return (
    <div className="flex h-full flex-col">
      <TopBar data={activeChart.data} refreshing={refresh.isPending} onRefresh={() => refresh.mutate()} />
      <div className="flex min-h-0 flex-1">
        <main className={`grid min-w-0 flex-1 bg-border ${GRID[layout]}`}>
          <ChartPane index={0} showActive={split} sync={paneSync[0]} />
          {split && <ChartPane index={1} showActive={split} sync={paneSync[1]} />}
        </main>
        {watchlistOpen && <Watchlist />}
      </div>
      {search.open && <SymbolSearch />}
      {/* key: remount per pane so the dialog's draft starts from that pane's settings */}
      {settingsPane !== null && <IndicatorSettings key={settingsPane} pane={settingsPane} />}
    </div>
  );
}
