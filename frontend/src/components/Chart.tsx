import {
  CandlestickSeries,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  LineType,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type LineWidth,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { Bar, ChartData, IndicatorSetting } from "../api/client";
import { formatPrice, formatShortDate } from "../lib/format";
import { appliesTo, indicatorLabel, isPriceOnly, seriesKeys, seriesLabel, timeKey, volumeData } from "../lib/series";
import { barAtOrBefore, dayNumber, dayToLogical, logicalToDay } from "../lib/sync";
import { theme } from "../theme";
import { ZonesPrimitive, type DrawZone } from "./zonesPrimitive";

const INITIAL_BARS = { D: 180, W: 150 } as const; // bars visible when a symbol/timeframe first loads
const RIGHT_OFFSET = 8;

const CANDLES = {
  upColor: theme.up,
  downColor: theme.down,
  borderUpColor: theme.up,
  borderDownColor: theme.down,
  wickUpColor: theme.up,
  wickDownColor: theme.down,
  borderVisible: true,
  wickVisible: true,
  lastValueVisible: true,
  priceLineVisible: true,
};
// Price-only symbols (mutual fund NAVs): candles have no range, so a close line is drawn instead.
// The candles stay (transparent) rather than hidden: zone bands, the crosshair and crosshair sync
// are attached to that series.
const TRANSPARENT = "rgba(0, 0, 0, 0)";
const INVISIBLE_CANDLES = {
  upColor: TRANSPARENT,
  downColor: TRANSPARENT,
  borderVisible: false,
  wickVisible: false,
  lastValueVisible: false,
  priceLineVisible: false,
}; // empty bars right of the latest one, unless the right edge is locked
const HOVER_EXTRA_WIDTH = 2; // px added to a hovered line
const HOVER_ANIMATION_MS = 150;

/** Visible X range as fractional days since epoch (see lib/sync.ts), so D and W charts align exactly. */
export interface SyncRange {
  from: number;
  to: number;
}

/** Lets a parent drive this chart from another one (crosshair + X-axis sync). */
export interface ChartHandle {
  /** Show the crosshair at the bar on/before `time` (null clears it). */
  showCrosshair: (time: string | null) => void;
  getRange: () => SyncRange | null;
  setRange: (range: SyncRange) => void;
  /** Widen the price axis to at least `px`, so stacked charts' plot areas line up. */
  setMinScaleWidth: (px: number) => void;
}

interface Props {
  data: ChartData;
  settings: IndicatorSetting[];
  onHover: (time: string | null) => void;
  /** User-originated crosshair moves only (not ones applied via the handle). */
  onCrosshair?: (time: string | null) => void;
  /** User-originated scroll/zoom only. */
  onRangeChange?: (range: SyncRange) => void;
  /** On load / symbol or timeframe change: a range to open at instead of the default zoom. */
  getInitialRange?: () => SyncRange | null;
  /** Current price-axis width in px, reported after renders. */
  onScaleWidth?: (px: number) => void;
  onReady?: (handle: ChartHandle | null) => void;
  /** Stop scrolling past the latest bar. */
  lockRightEdge?: boolean;
}

/** With the right edge locked, pull the view back if it shows space past the latest bar. */
function clampToLatest(chart: IChartApi, barCount: number) {
  const range = chart.timeScale().getVisibleLogicalRange();
  if (range && range.to > barCount - 1) chart.timeScale().scrollToRealTime(); // latest bar at the right edge
}

interface ChartRefs {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  /** Close line, shown instead of candles for price-only symbols. */
  closeLine: ISeriesApi<"Line">;
  volume: ISeriesApi<"Histogram">;
  lines: Map<string, ISeriesApi<"Line">>;
  /** Label/colour/base width per line series, for hover. Refreshed whenever settings change. */
  lineInfo: Map<ISeriesApi<"Line">, { label: string; color: string; width: number }>;
  /** Line currently drawn thicker because the cursor is on it. */
  highlighted: ISeriesApi<"Line"> | null;
  /** In-flight width animations, and each animated line's current (fractional) width. */
  widths: Map<ISeriesApi<"Line">, { current: number; raf: number }>;
  /** Support-zone bands (drawn behind the candles) and their price-axis labels. */
  zones: ZonesPrimitive;
  zoneLabels: IPriceLine[];
}

interface Tooltip {
  label: string;
  color: string;
  /** Value for a line; range, touches and date for a support zone. */
  text: string;
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

export function Chart(props: Props) {
  const { data, settings } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const refs = useRef<ChartRefs | null>(null);
  const viewKey = useRef<string>("");
  // Latest callbacks, read by chart event handlers that are subscribed once at creation.
  const callbacks = useRef(props);
  callbacks.current = props;
  const bars = useRef<{ list: Bar[]; times: string[]; days: number[] }>({ list: [], times: [], days: [] });
  // Set while applying a synced crosshair/range, so the resulting chart events aren't echoed back
  // to the other chart (which would bounce between the two forever).
  const syncingCrosshair = useRef(false);
  const syncingRange = useRef(0);

  // Range-change events can arrive a frame or two after the change, so release over 2 frames.
  const releaseRangeGuard = () => requestAnimationFrame(() => requestAnimationFrame(() => syncingRange.current--));
  // Price-axis width is only known after the chart renders; skip if the chart was removed meanwhile.
  const reportScaleWidth = () =>
    requestAnimationFrame(() => {
      const chart = refs.current?.chart;
      if (chart) callbacks.current.onScaleWidth?.(chart.priceScale("right").width());
    });
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
      timeScale: { borderColor: theme.border, rightOffset: RIGHT_OFFSET },
    });
    const candles = chart.addSeries(CandlestickSeries, CANDLES);
    const closeLine = chart.addSeries(LineSeries, { color: theme.accent, lineWidth: 2, visible: false });
    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    chart.panes()[0].setStretchFactor(4);
    chart.panes()[1].setStretchFactor(1);
    chart.subscribeCrosshairMove((param) => {
      const time = timeKey(param.time);
      callbacks.current.onHover(time);
      if (syncingCrosshair.current) return;
      callbacks.current.onCrosshair?.(time);
      // hoveredSeries is set when the cursor is on a series' line (the library does the hit-testing).
      const hovered = param.hoveredSeries as ISeriesApi<"Line"> | undefined;
      const r = refs.current;
      const info = hovered && r?.lineInfo.get(hovered);
      if (r) highlight(r, info ? hovered! : null);
      if (!param.point) return setTooltip(null);
      // Lines take precedence; otherwise a support zone under the cursor (price pane only).
      const zone = !info && param.paneIndex === 0 ? r?.zones.zoneAt(param.point.x, param.point.y) : null;
      if (!info && !zone) return setTooltip(null);
      const point = info ? (param.seriesData.get(hovered!) as LineData | undefined) : undefined;
      setTooltip({
        label: info ? info.label : zone!.tooltip.label,
        color: info ? info.color : zone!.color,
        text: info ? formatPrice(point?.value) : zone!.tooltip.text,
        x: param.point.x,
        y: param.point.y,
        flip: param.point.x > chart.paneSize(0).width - 220,
      });
    });
    // Logical (bar-index) ranges, not time ranges: they're fractional and extend into the empty
    // space past the last bar, which time ranges can't express.
    const getRange = (): SyncRange | null => {
      const lr = chart.timeScale().getVisibleLogicalRange();
      const from = lr && logicalToDay(bars.current.days, lr.from);
      const to = lr && logicalToDay(bars.current.days, lr.to);
      return from != null && to != null ? { from, to } : null;
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      reportScaleWidth(); // zooming can change the price labels' width
      if (syncingRange.current > 0) return;
      const range = getRange();
      if (range) callbacks.current.onRangeChange?.(range);
    });
    const zones = new ZonesPrimitive();
    candles.attachPrimitive(zones);
    refs.current = {
      chart, candles, closeLine, volume, lines: new Map(), lineInfo: new Map(), highlighted: null, widths: new Map(),
      zones, zoneLabels: [],
    };

    const handle: ChartHandle = {
      showCrosshair: (time) => {
        const i = time == null ? -1 : barAtOrBefore(bars.current.times, time);
        const bar = bars.current.list[i];
        syncingCrosshair.current = true;
        try {
          if (bar) chart.setCrosshairPosition(bar.close, bar.time, candles);
          else chart.clearCrosshairPosition();
        } finally {
          syncingCrosshair.current = false;
        }
        callbacks.current.onHover(bar?.time ?? null);
      },
      getRange,
      setRange: (range) => {
        const from = dayToLogical(bars.current.days, range.from);
        const to = dayToLogical(bars.current.days, range.to);
        if (from == null || to == null) return;
        syncingRange.current++;
        chart.timeScale().setVisibleLogicalRange({ from, to });
        releaseRangeGuard();
      },
      setMinScaleWidth: (px) => chart.applyOptions({ rightPriceScale: { minimumWidth: px } }),
    };
    callbacks.current.onReady?.(handle);

    return () => {
      callbacks.current.onReady?.(null);
      if (refs.current) stopWidthAnimations(refs.current);
      chart.remove();
      refs.current = null;
    };
  }, []);

  // Push data + indicator styles into the chart.
  useEffect(() => {
    const r = refs.current;
    if (!r) return;
    // setData and the view reset below both move the visible range. Neither is a user scroll, so
    // don't push them onto the other chart; a newly loaded chart *pulls* the other's range instead.
    // Events can arrive a frame or two later, so hold the guard across 2 frames.
    syncingRange.current++;
    const times = data.bars.map((b) => b.time);
    bars.current = { list: data.bars, times, days: times.map(dayNumber) };
    r.candles.setData(data.bars);
    r.volume.setData(volumeData(data.bars, theme.upVolume, theme.downVolume));
    const priceOnly = isPriceOnly(data.bars);
    r.candles.applyOptions(priceOnly ? INVISIBLE_CANDLES : CANDLES);
    r.closeLine.applyOptions({ visible: priceOnly });
    r.closeLine.setData(priceOnly ? data.bars.map((b) => ({ time: b.time, value: b.close })) : []);
    // Funds report no volume: collapse that pane rather than show an empty one.
    r.volume.applyOptions({ visible: !priceOnly });
    r.chart.panes()[1]?.setStretchFactor(priceOnly ? 0.0001 : 1);

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
    // Support zones: bands + an axis label per zone ("212.40 ×4").
    const drawZones: DrawZone[] = [];
    for (const label of r.zoneLabels) r.candles.removePriceLine(label);
    r.zoneLabels = [];
    for (const s of settings) {
      if (s.kind !== "sr" || !s.visible || !appliesTo(s, data.tf)) continue;
      for (const z of data.zones?.[s.id] ?? []) {
        const touches = `${z.touches} touch${z.touches === 1 ? "" : "es"}`;
        const range = z.low === z.high ? formatPrice(z.low) : `${formatPrice(z.high)}–${formatPrice(z.low)}`;
        drawZones.push({
          low: z.low, high: z.high, color: s.color, startDay: dayNumber(z.first),
          tooltip: { label: indicatorLabel(s), text: `${range} · ${touches} · last ${formatShortDate(z.last)}` },
        });
        r.zoneLabels.push(
          r.candles.createPriceLine({
            price: (z.low + z.high) / 2, color: s.color, lineVisible: false, axisLabelVisible: true,
            title: `×${z.touches}`,
          }),
        );
      }
    }
    r.zones.setZones(drawZones, bars.current.days);

    for (const [key, line] of r.lines) {
      if (!wanted.has(key)) {
        r.chart.removeSeries(line);
        r.lines.delete(key);
      }
    }

    // Reset the view only when the symbol or timeframe changes, not on refreshes/setting edits.
    // When X-synced with another chart, open at its range; otherwise at the default zoom.
    const key = `${data.symbol}:${data.tf}`;
    if (viewKey.current !== key) {
      viewKey.current = key;
      const synced = callbacks.current.getInitialRange?.();
      const from = synced && dayToLogical(bars.current.days, synced.from);
      const to = synced && dayToLogical(bars.current.days, synced.to);
      const n = data.bars.length;
      r.chart
        .timeScale()
        .setVisibleLogicalRange(
          from != null && to != null
            ? { from, to }
            : { from: Math.max(0, n - INITIAL_BARS[data.tf]), to: n - 1 + RIGHT_OFFSET },
        );
      if (props.lockRightEdge) clampToLatest(r.chart, n);
    }
    releaseRangeGuard();
    // New data can change the price labels' width (e.g. 99.00 -> 1,082.28).
    reportScaleWidth();
  }, [data, settings]);

  // Right-edge lock. Turning it on while scrolled into the future snaps back to the latest bar
  // (a user action, so with X-sync on the other chart follows).
  const lockRightEdge = props.lockRightEdge ?? false;
  useEffect(() => {
    const r = refs.current;
    if (!r) return;
    r.chart.applyOptions({ timeScale: { fixRightEdge: lockRightEdge, rightOffset: lockRightEdge ? 0 : RIGHT_OFFSET } });
    if (lockRightEdge) clampToLatest(r.chart, bars.current.list.length);
  }, [lockRightEdge]);

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
          <span style={{ color: tooltip.color }}>{tooltip.text}</span>
        </div>
      )}
    </div>
  );
}
