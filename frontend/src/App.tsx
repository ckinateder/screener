import { useEffect, useMemo, useState } from "react";
import type { ChartData, IndicatorSetting } from "./api/client";
import { useChart, useRefreshChart, useSaveSettings, useSettings, useWatchlist } from "./api/hooks";
import { Chart } from "./components/Chart";
import { IndicatorSettings } from "./components/IndicatorSettings";
import { Legend } from "./components/Legend";
import { SymbolSearch } from "./components/SymbolSearch";
import { TopBar } from "./components/TopBar";
import { Spinner } from "./components/ui/Spinner";
import { Watchlist } from "./components/Watchlist";
import { makeLegendLookup } from "./lib/series";
import { buildUrlSearch } from "./lib/urlState";
import { useUi } from "./store";

const FALLBACK_SYMBOL = "SPY";

export default function App() {
  const { symbol, tf, setSymbol, search, settingsOpen, watchlistOpen, openSearch } = useUi();
  const watchlist = useWatchlist();
  const settings = useSettings();
  const chart = useChart(symbol, tf);
  const refresh = useRefreshChart(symbol, tf);

  // No symbol in the URL: open the first watchlist entry, else SPY.
  useEffect(() => {
    if (symbol || watchlist.isLoading) return;
    setSymbol(watchlist.data?.[0]?.symbol ?? FALLBACK_SYMBOL);
  }, [symbol, watchlist.isLoading, watchlist.data, setSymbol]);

  useEffect(() => {
    if (symbol) window.history.replaceState(null, "", buildUrlSearch({ symbol, tf }));
    document.title = symbol ? `${symbol} · Kaching` : "Kaching";
  }, [symbol, tf]);

  const data = chart.data;
  const loading = chart.isFetching && (chart.isPlaceholderData || !data);

  return (
    <div className="flex h-full flex-col">
      <TopBar data={data} refreshing={refresh.isPending} onRefresh={() => refresh.mutate()} />
      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1">
          {data && settings.data && <ChartPanel data={data} settings={settings.data} />}
          {loading && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-bg/40">
              <Spinner size={28} />
            </div>
          )}
          {chart.error && !loading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-bg">
              <p className="text-base">{chart.error.message}</p>
              <button onClick={() => openSearch("open")} className="rounded bg-accent px-4 py-1.5 text-white">
                Search symbols
              </button>
            </div>
          )}
        </main>
        {watchlistOpen && <Watchlist />}
      </div>
      {search.open && <SymbolSearch />}
      {settingsOpen && settings.data && <IndicatorSettings />}
    </div>
  );
}

/** Chart + legend. Hover state lives here so mouse moves don't re-render the rest of the app. */
function ChartPanel({ data, settings }: { data: ChartData; settings: IndicatorSetting[] }) {
  const [hoverTime, setHoverTime] = useState<string | null>(null);
  const lookup = useMemo(() => makeLegendLookup(data), [data]);
  const save = useSaveSettings();
  const setSettingsOpen = useUi((s) => s.setSettingsOpen);

  const toggle = (id: string) => save.mutate(settings.map((s) => (s.id === id ? { ...s, visible: !s.visible } : s)));

  return (
    <>
      <Chart data={data} settings={settings} onHover={setHoverTime} />
      <Legend
        data={data}
        settings={settings}
        snapshot={lookup(hoverTime)}
        onToggle={toggle}
        onOpenSettings={() => setSettingsOpen(true)}
      />
    </>
  );
}
