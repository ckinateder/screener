import { describe, expect, it } from "vitest";
import type { ChartData, IndicatorSetting } from "../api/client";
import { appliesTo, indicatorLabel, seriesLabel, makeLegendLookup, paramsChanged, seriesKeys, timeKey, volumeData } from "./series";

const ema: IndicatorSetting = { id: "d_ema_9", kind: "ema", tf: "D", length: 9, color: "#fff000", width: 2, visible: true };
const kc: IndicatorSetting = {
  id: "w_kc", kind: "kc", tf: "W", ema_length: 20, atr_length: 10, multiplier: 2, color: "#000fff", width: 1, visible: true,
};

describe("series helpers", () => {
  it("maps settings to API series keys", () => {
    expect(seriesKeys(ema)).toEqual(["d_ema_9"]);
    expect(seriesKeys(kc)).toEqual(["w_kc:upper", "w_kc:mid", "w_kc:lower"]);
  });

  it("hides daily indicators on the weekly chart", () => {
    expect(appliesTo(ema, "D")).toBe(true);
    expect(appliesTo(ema, "W")).toBe(false);
    expect(appliesTo(kc, "D")).toBe(true);
    expect(appliesTo(kc, "W")).toBe(true);
  });

  it("labels indicators", () => {
    expect(indicatorLabel(ema)).toBe("EMA 9");
    expect(indicatorLabel(kc)).toBe("W KC 20 2 10");
    expect(seriesLabel(ema, "d_ema_9")).toBe("EMA 9");
    expect(seriesLabel(kc, "w_kc:upper")).toBe("W KC 20 2 10 · Upper");
  });

  it("detects parameter changes but ignores style changes", () => {
    expect(paramsChanged([ema, kc], [{ ...ema, color: "#123456", visible: false, width: 4 }, kc])).toBe(false);
    expect(paramsChanged([ema, kc], [ema, { ...kc, multiplier: 1.5 }])).toBe(true);
  });

  it("colours volume by candle direction", () => {
    const bars = [
      { time: "2024-01-01", open: 1, high: 2, low: 0, close: 2, volume: 10 },
      { time: "2024-01-02", open: 2, high: 2, low: 0, close: 1, volume: 20 },
    ];
    expect(volumeData(bars, "up", "down").map((v) => v.color)).toEqual(["up", "down"]);
  });

  it("normalises crosshair times", () => {
    expect(timeKey("2024-03-05")).toBe("2024-03-05");
    expect(timeKey({ year: 2024, month: 3, day: 5 })).toBe("2024-03-05");
    expect(timeKey(undefined)).toBeNull();
  });
});

describe("makeLegendLookup", () => {
  const data: ChartData = {
    symbol: "AAPL", name: null, exchange: null, tf: "D", healed: false, stale: false,
    bars: [
      { time: "2024-01-01", open: 1, high: 2, low: 0, close: 10, volume: 1 },
      { time: "2024-01-02", open: 1, high: 2, low: 0, close: 11, volume: 1 },
      { time: "2024-01-03", open: 1, high: 2, low: 0, close: 12, volume: 1 },
    ],
    indicators: { d_ema_9: [{ time: "2024-01-02", value: 10.5 }, { time: "2024-01-03", value: 11 }] },
  };
  const lookup = makeLegendLookup(data);

  it("returns the hovered bar with previous close and indicator values", () => {
    const snap = lookup("2024-01-02");
    expect(snap.bar?.close).toBe(11);
    expect(snap.prevClose).toBe(10);
    expect(snap.values.d_ema_9).toBe(10.5);
  });

  it("defaults to the latest bar when not hovering", () => {
    expect(lookup(null).bar?.time).toBe("2024-01-03");
  });

  it("handles indicator warm-up gaps and the first bar", () => {
    const snap = lookup("2024-01-01");
    expect(snap.prevClose).toBeNull();
    expect(snap.values.d_ema_9).toBeUndefined();
  });
});
