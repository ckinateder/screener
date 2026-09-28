import type { Bar, ChartData, IndicatorSetting, Point, Tf } from "../api/client";

export const KC_PARTS = ["upper", "mid", "lower"] as const;

/** API series keys produced by one indicator setting. */
export function seriesKeys(setting: IndicatorSetting): string[] {
  return setting.kind === "ema" ? [setting.id] : KC_PARTS.map((p) => `${setting.id}:${p}`);
}

/** Daily indicators aren't meaningful on weekly candles, so the W chart only shows weekly ones. */
export function appliesTo(setting: IndicatorSetting, tf: Tf): boolean {
  return tf === "D" || setting.tf === "W";
}

export function indicatorLabel(s: IndicatorSetting): string {
  const prefix = s.tf === "W" ? "W " : "";
  return s.kind === "ema" ? `${prefix}EMA ${s.length}` : `${prefix}KC ${s.ema_length} ${s.multiplier} ${s.atr_length}`;
}

/** Label for one drawn line, e.g. "EMA 21" or "W KC 20 2 10 · Upper". */
export function seriesLabel(s: IndicatorSetting, key: string): string {
  const part = key.split(":")[1];
  return part ? `${indicatorLabel(s)} · ${part[0].toUpperCase()}${part.slice(1)}` : indicatorLabel(s);
}

const PARAM_FIELDS = ["length", "ema_length", "atr_length", "multiplier"] as const;

/** True when any calculation parameter differs (style/visibility changes don't need a recompute). */
export function paramsChanged(a: IndicatorSetting[], b: IndicatorSetting[]): boolean {
  const byId = new Map(a.map((s) => [s.id, s]));
  return b.some((s) => {
    const prev = byId.get(s.id);
    return !prev || PARAM_FIELDS.some((f) => prev[f] !== s[f]);
  });
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
