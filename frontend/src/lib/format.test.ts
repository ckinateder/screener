import { describe, expect, it } from "vitest";
import { changeClass, formatChange, formatPct, formatPrice, formatVolume } from "./format";

describe("format", () => {
  it("formats prices with extra precision under $1", () => {
    expect(formatPrice(341.071)).toBe("341.07");
    expect(formatPrice(0.12345)).toBe("0.1235");
    expect(formatPrice(0)).toBe("0.00");
    expect(formatPrice(null)).toBe("—");
    expect(formatPrice(NaN)).toBe("—");
  });

  it("signs changes and percentages", () => {
    expect(formatChange(1.5)).toBe("+1.50");
    expect(formatChange(-1.5)).toBe("-1.50");
    expect(formatChange(0.49)).toBe("+0.49");
    expect(formatPct(2.345)).toBe("+2.35%"); // toFixed rounding
    expect(formatPct(-0.1)).toBe("-0.10%");
    expect(formatPct(undefined)).toBe("—");
  });

  it("abbreviates volume", () => {
    expect(formatVolume(950)).toBe("950");
    expect(formatVolume(12_340)).toBe("12.34K");
    expect(formatVolume(45_600_000)).toBe("45.60M");
    expect(formatVolume(2_100_000_000)).toBe("2.10B");
  });

  it("colours changes", () => {
    expect(changeClass(1)).toBe("text-up");
    expect(changeClass(-1)).toBe("text-down");
    expect(changeClass(0)).toBe("text-muted");
    expect(changeClass(null)).toBe("text-muted");
  });
});
