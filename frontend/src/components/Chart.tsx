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
  type LineData,
  type LineWidth,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { ChartData, IndicatorSetting } from "../api/client";
import { formatPrice } from "../lib/format";
import { appliesTo, seriesKeys, seriesLabel, timeKey, volumeData } from "../lib/series";
import { theme } from "../theme";

const INITIAL_BARS = { D: 180, W: 150 } as const; // bars visible when a symbol/timeframe first loads
const HOVER_EXTRA_WIDTH = 2; // px added to a hovered line
const HOVER_ANIMATION_MS = 150;

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
  /** Label/colour/base width per line series, for hover. Refreshed whenever settings change. */
  lineInfo: Map<ISeriesApi<"Line">, { label: string; color: string; width: number }>;
  /** Line currently drawn thicker because the cursor is on it. */
  highlighted: ISeriesApi<"Line"> | null;
  /** In-flight width animations, and each animated line's current (fractional) width. */
  widths: Map<ISeriesApi<"Line">, { current: number; raf: number }>;
}

interface Tooltip {
  label: string;
  color: string;
  value: number | undefined;
  x: number;
  y: number;
  flip: boolean; // near the right edge: render to the left of the cursor
}

/** Thicken the hovered line (TradingView-style) and restore the previously hovered one. */
function highlight(r: ChartRefs, line: ISeriesApi<"Line"> | null) {
  if (r.highlighted === line) return;
  const prevLine = r.highlighted;
  // Update before applyOptions: it synchronously re-fires crosshairMove, which re-enters here.
  r.highlighted = line;
  const prev = prevLine && r.lineInfo.get(prevLine);
  if (prev) animateWidth(r, prevLine!, prev.width, prev.width);
  const next = line && r.lineInfo.get(line);
  if (next) animateWidth(r, line!, next.width, next.width + HOVER_EXTRA_WIDTH);
}

/** Ease a line's width to `target`. Canvas lines can't use CSS transitions, so tween per frame. */
function animateWidth(r: ChartRefs, line: ISeriesApi<"Line">, base: number, target: number) {
  const state = r.widths.get(line) ?? { current: base, raf: 0 };
  cancelAnimationFrame(state.raf); // reversing mid-animation continues from the current width
  r.widths.set(line, state);
  const from = state.current;
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / HOVER_ANIMATION_MS);
    state.current = from + (target - from) * (1 - (1 - t) ** 3); // ease-out cubic
    // LineWidth is typed 1-4, but the line renderer draws any (fractional) width.
    line.applyOptions({ lineWidth: state.current as LineWidth });
    state.raf = t < 1 ? requestAnimationFrame(step) : 0;
  };
  state.raf = requestAnimationFrame(step);
}

function stopWidthAnimations(r: ChartRefs) {
  for (const { raf } of r.widths.values()) cancelAnimationFrame(raf);
  r.widths.clear();
  r.highlighted = null;
}

export function Chart({ data, settings, onHover }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const refs = useRef<ChartRefs | null>(null);
  const viewKey = useRef<string>("");
  const onHoverRef = useRef(onHover);
  onHoverRef.current = onHover;
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

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
    chart.subscribeCrosshairMove((param) => {
      onHoverRef.current(timeKey(param.time));
      // hoveredSeries is set when the cursor is on a series' line (the library does the hit-testing).
      const hovered = param.hoveredSeries as ISeriesApi<"Line"> | undefined;
      const r = refs.current;
      const info = hovered && r?.lineInfo.get(hovered);
      if (r) highlight(r, info ? hovered! : null);
      if (!info || !param.point) return setTooltip(null);
      const point = param.seriesData.get(hovered) as LineData | undefined;
      setTooltip({
        label: info.label,
        color: info.color,
        value: point?.value,
        x: param.point.x,
        y: param.point.y,
        flip: param.point.x > chart.paneSize(0).width - 220,
      });
    });
    refs.current = { chart, candles, volume, lines: new Map(), lineInfo: new Map(), highlighted: null, widths: new Map() };
    return () => {
      if (refs.current) stopWidthAnimations(refs.current);
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

    // Widths are reset to their configured values below; drop any hover animation state.
    stopWidthAnimations(r);
    const wanted = new Set<string>();
    r.lineInfo.clear();
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
        r.lineInfo.set(line, { label: seriesLabel(s, key), color: s.color, width: s.width });
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

  return (
    <div ref={containerRef} className="absolute inset-0">
      {tooltip && (
        <div
          className="pointer-events-none absolute z-20 flex items-center gap-2 whitespace-nowrap rounded border border-border bg-pane/95 px-2 py-1 shadow-lg"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: `translate(${tooltip.flip ? "calc(-100% - 12px)" : "12px"}, calc(-100% - 8px))`,
          }}
        >
          <span className="size-2 rounded-full" style={{ background: tooltip.color }} />
          <span>{tooltip.label}</span>
          <span style={{ color: tooltip.color }}>{formatPrice(tooltip.value)}</span>
        </div>
      )}
    </div>
  );
}
