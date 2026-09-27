import {
  CandlestickSeries,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  LineType,
  type IChartApi,
  type ISeriesApi,
  type LineWidth,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { ChartData, IndicatorSetting } from "../api/client";
import { appliesTo, seriesKeys, timeKey, volumeData } from "../lib/series";
import { theme } from "../theme";

const INITIAL_BARS = { D: 180, W: 150 } as const; // bars visible when a symbol/timeframe first loads

interface Props {
  data: ChartData;
  settings: IndicatorSetting[];
  onHover: (time: string | null) => void;
}

interface ChartRefs {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  lines: Map<string, ISeriesApi<"Line">>;
}

export function Chart({ data, settings, onHover }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const refs = useRef<ChartRefs | null>(null);
  const viewKey = useRef<string>("");
  const onHoverRef = useRef(onHover);
  onHoverRef.current = onHover;

  // Create the chart once; series are updated in place below.
  useEffect(() => {
    const chart = createChart(containerRef.current!, {
      autoSize: true,
      layout: {
        background: { color: theme.bg },
        textColor: theme.text,
        fontFamily: theme.font,
        fontSize: 12,
        attributionLogo: false,
        panes: { separatorColor: theme.border, separatorHoverColor: theme.border },
      },
      grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: theme.crosshair, labelBackgroundColor: "#363a45" },
        horzLine: { color: theme.crosshair, labelBackgroundColor: "#363a45" },
      },
      rightPriceScale: { borderColor: theme.border },
      timeScale: { borderColor: theme.border, rightOffset: 8 },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: theme.up,
      downColor: theme.down,
      borderUpColor: theme.up,
      borderDownColor: theme.down,
      wickUpColor: theme.up,
      wickDownColor: theme.down,
    });
    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    chart.panes()[0].setStretchFactor(4);
    chart.panes()[1].setStretchFactor(1);
    chart.subscribeCrosshairMove((param) => onHoverRef.current(timeKey(param.time)));
    refs.current = { chart, candles, volume, lines: new Map() };
    return () => {
      chart.remove();
      refs.current = null;
    };
  }, []);

  // Push data + indicator styles into the chart.
  useEffect(() => {
    const r = refs.current;
    if (!r) return;
    r.candles.setData(data.bars);
    r.volume.setData(volumeData(data.bars, theme.upVolume, theme.downVolume));

    const wanted = new Set<string>();
    for (const s of settings) {
      if (!appliesTo(s, data.tf)) continue;
      for (const key of seriesKeys(s)) {
        wanted.add(key);
        let line = r.lines.get(key);
        if (!line) {
          line = r.chart.addSeries(LineSeries, {
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          r.lines.set(key, line);
        }
        line.applyOptions({
          color: s.color,
          lineWidth: s.width as LineWidth,
          visible: s.visible,
          lineStyle: key.endsWith(":mid") ? LineStyle.Dotted : LineStyle.Solid,
          // Weekly values drawn on daily candles change once a week: draw them as steps.
          lineType: data.tf === "D" && s.tf === "W" ? LineType.WithSteps : LineType.Simple,
        });
        line.setData(data.indicators[key] ?? []);
      }
    }
    for (const [key, line] of r.lines) {
      if (!wanted.has(key)) {
        r.chart.removeSeries(line);
        r.lines.delete(key);
      }
    }

    // Reset the view only when the symbol or timeframe changes, not on refreshes/setting edits.
    const key = `${data.symbol}:${data.tf}`;
    if (viewKey.current !== key) {
      viewKey.current = key;
      const n = data.bars.length;
      r.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - INITIAL_BARS[data.tf]), to: n + 8 });
    }
  }, [data, settings]);

  return <div ref={containerRef} className="absolute inset-0" />;
}
