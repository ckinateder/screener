import { useMemo, useState } from "react";
import type { ChartData, IndicatorSetting } from "../api/client";
import { useChart, useSaveSettings, useSettings } from "../api/hooks";
import { makeLegendLookup } from "../lib/series";
import { useUi, type PaneIndex } from "../store";
import { Chart, type ChartHandle, type SyncRange } from "./Chart";
import { Legend } from "./Legend";
import { Spinner } from "./ui/Spinner";

export interface PaneSync {
  onCrosshair: (time: string | null) => void;
  onRangeChange: (range: SyncRange) => void;
  getInitialRange: () => SyncRange | null;
  onScaleWidth: (px: number) => void;
  onReady: (handle: ChartHandle | null) => void;
}

interface Props {
  index: PaneIndex;
  /** Draw the active outline (only meaningful when more than one pane is shown). */
  showActive: boolean;
  sync: PaneSync;
}

/** One chart slot: data fetching, loading/error overlays, legend, and click-to-activate. */
export function ChartPane({ index, showActive, sync }: Props) {
  const pane = useUi((s) => s.panes[index]);
  const isActive = useUi((s) => s.active === index);
  const setActive = useUi((s) => s.setActive);
  const openSearch = useUi((s) => s.openSearch);
  const chart = useChart(index, pane.symbol, pane.tf);
  const settings = useSettings(index);
  const data = chart.data;
  const loading = chart.isFetching && (chart.isPlaceholderData || !data);

  return (
    <div className="relative min-h-0 min-w-0 bg-bg" onMouseDown={() => setActive(index)}>
      {/* Overlay rather than a border/outline on this div: the absolutely positioned canvas would cover it. */}
      {showActive && isActive && <div className="pointer-events-none absolute inset-0 z-30 border-2 border-accent" />}
      {data && settings.data && <ChartWithLegend index={index} data={data} settings={settings.data} sync={sync} />}
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-bg/40">
          <Spinner size={28} />
        </div>
      )}
      {chart.error && !loading && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-bg">
          <p className="text-base">{chart.error.message}</p>
          <button
            onClick={() => {
              setActive(index);
              openSearch("open");
            }}
            className="rounded bg-accent px-4 py-1.5 text-white"
          >
            Search symbols
          </button>
        </div>
      )}
    </div>
  );
}

/** Chart + legend. Hover state lives here so mouse moves don't re-render the rest of the app. */
interface ChartWithLegendProps {
  index: PaneIndex;
  data: ChartData;
  settings: IndicatorSetting[];
  sync: PaneSync;
}

function ChartWithLegend({ index, data, settings, sync }: ChartWithLegendProps) {
  const [hoverTime, setHoverTime] = useState<string | null>(null);
  const lookup = useMemo(() => makeLegendLookup(data), [data]);
  const save = useSaveSettings(index);
  const lockRightEdge = useUi((s) => s.lockRightEdge);
  const openSettings = useUi((s) => s.openSettings);

  const toggle = (id: string) => save.mutate(settings.map((s) => (s.id === id ? { ...s, visible: !s.visible } : s)));

  return (
    <>
      <Chart
        data={data}
        settings={settings}
        onHover={setHoverTime}
        onCrosshair={sync.onCrosshair}
        onRangeChange={sync.onRangeChange}
        getInitialRange={sync.getInitialRange}
        onScaleWidth={sync.onScaleWidth}
        onReady={sync.onReady}
        lockRightEdge={lockRightEdge}
      />
      <Legend
        data={data}
        settings={settings}
        snapshot={lookup(hoverTime)}
        onToggle={toggle}
        onOpenSettings={() => openSettings(index)}
      />
    </>
  );
}
