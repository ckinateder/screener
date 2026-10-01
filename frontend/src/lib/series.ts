import type { Bar, ChartData, IndicatorSetting, Point, Tf } from "../api/client";

export const KC_PARTS = ["upper", "mid", "lower"] as const;

/** API series keys produced by one indicator setting. */
export function seriesKeys(setting: IndicatorSetting): string[] {
  if (setting.kind === "ema" || setting.kind === "sma") return [setting.id];
  if (setting.kind === "kc") return KC_PARTS.map((p) => `${setting.id}:${p}`);
  return []; // "sr" support zones are drawn as bands, not line series
}

/** Daily indicators aren't meaningful on weekly candles, so the W chart only shows weekly ones. */
export function appliesTo(setting: IndicatorSetting, tf: Tf): boolean {
  return tf === "D" || setting.tf === "W";
}

export function indicatorLabel(s: IndicatorSetting): string {
  if (s.kind === "sr") return `${s.tf} Support`; // both get a prefix: there's no unprefixed "Support"
  const prefix = s.tf === "W" ? "W " : "";
  if (s.kind === "ema" || s.kind === "sma") return `${prefix}${s.kind.toUpperCase()} ${s.length}`;
  return `${prefix}KC ${s.ema_length} ${s.multiplier} ${s.atr_length}`;
}

/** Label for one drawn line, e.g. "EMA 21" or "W KC 20 2 10 · Upper". */
export function seriesLabel(s: IndicatorSetting, key: string): string {
  const part = key.split(":")[1];
  return part ? `${indicatorLabel(s)} · ${part[0].toUpperCase()}${part.slice(1)}` : indicatorLabel(s);
}

const PARAM_FIELDS = [
  "length", "ema_length", "atr_length", "multiplier",
  "pivot", "tolerance", "lookback_years", "max_zones", "min_touches",
] as const;

/** True when any calculation parameter differs (style/visibility changes don't need a recompute). */
export function paramsChanged(a: IndicatorSetting[], b: IndicatorSetting[]): boolean {
  const byId = new Map(a.map((s) => [s.id, s]));
  return b.some((s) => {
    const prev = byId.get(s.id);
    return !prev || PARAM_FIELDS.some((f) => prev[f] !== s[f]);
  });
}

/**
 * True for price-only symbols (mutual funds report one NAV a day: open = high = low = close),
 * which draw as nothing with candles. Judged on recent bars, allowing a few stray ones.
 */
export function isPriceOnly(bars: Bar[], sample = 100): boolean {
  const recent = bars.slice(-sample);
  if (recent.length === 0) return false;
  return recent.filter((b) => b.high === b.low).length / recent.length >= 0.95;
}

export function volumeData(bars: Bar[], upColor: string, downColor: string) {
  return bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? upColor : downColor }));
}

/** Lightweight Charts reports crosshair time as it was given (string) or as a BusinessDay object. */
export function timeKey(time: unknown): string | null {
  if (time == null) return null;
  if (typeof time === "string") return time;
  if (typeof time === "object" && "year" in time && "month" in time && "day" in time) {
    const { year, month, day } = time as { year: number; month: number; day: number };
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }
  return null;
}

export interface LegendSnapshot {
  bar: Bar | null;
  prevClose: number | null;
  values: Record<string, number | undefined>;
}

/** Builds a lookup that returns bar + indicator values at a time (or the latest bar when time is null). */
export function makeLegendLookup(data: ChartData): (time: string | null) => LegendSnapshot {
  const barIndex = new Map(data.bars.map((b, i) => [b.time, i]));
  const indicatorMaps = Object.entries(data.indicators).map(
    ([key, points]) => [key, new Map(points.map((p: Point) => [p.time, p.value]))] as const,
  );
  return (time) => {
    const i = time != null && barIndex.has(time) ? barIndex.get(time)! : data.bars.length - 1;
    const bar = data.bars[i] ?? null;
    const values: Record<string, number | undefined> = {};
    if (bar) for (const [key, map] of indicatorMaps) values[key] = map.get(bar.time);
    return { bar, prevClose: i > 0 ? data.bars[i - 1].close : null, values };
  };
}
