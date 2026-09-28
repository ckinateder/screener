import { describe, expect, it } from "vitest";
import { barAtOrBefore, dayNumber, dayToLogical, logicalToDay } from "./sync";

const weekly = ["2024-01-01", "2024-01-08", "2024-01-15"]; // Monday labels
const daily = ["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08", "2024-01-09"];

describe("barAtOrBefore", () => {
  it("finds exact matches", () => {
    expect(barAtOrBefore(weekly, "2024-01-08")).toBe(1);
  });

  it("maps a daily date to the week containing it", () => {
    expect(weekly[barAtOrBefore(weekly, "2024-01-11")]).toBe("2024-01-08");
    expect(weekly[barAtOrBefore(weekly, "2024-01-19")]).toBe("2024-01-15");
  });

  it("maps a weekly Monday to that day, or the prior trading day on a holiday", () => {
    expect(daily[barAtOrBefore(daily, "2024-01-08")]).toBe("2024-01-08");
    expect(daily[barAtOrBefore(daily, "2024-01-07")]).toBe("2024-01-05");
  });

  it("returns -1 before the first bar or for empty input", () => {
    expect(barAtOrBefore(weekly, "2023-12-31")).toBe(-1);
    expect(barAtOrBefore([], "2024-01-01")).toBe(-1);
  });
});

describe("logical <-> day mapping", () => {
  // Mon-Fri, then Mon: a weekend gap between index 4 and 5.
  const dailyDays = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"].map(dayNumber);
  const weeklyDays = ["2024-01-01", "2024-01-08", "2024-01-15"].map(dayNumber);

  it("maps bar positions onto their dates", () => {
    expect(logicalToDay(dailyDays, 5)).toBe(dayNumber("2024-01-08"));
    expect(logicalToDay(weeklyDays, 1)).toBe(dayNumber("2024-01-08"));
  });

  it("interpolates between bars, including across gaps", () => {
    expect(logicalToDay(weeklyDays, 0.5)).toBe(dayNumber("2024-01-01") + 3.5);
    expect(logicalToDay(dailyDays, 4.5)).toBe(dayNumber("2024-01-05") + 1.5); // Fri -> Mon gap
  });

  it("extrapolates beyond the data with the average bar spacing", () => {
    expect(logicalToDay(weeklyDays, 4)).toBe(dayNumber("2024-01-29"));
    expect(logicalToDay(weeklyDays, -1)).toBe(dayNumber("2023-12-25"));
  });

  it("round-trips", () => {
    for (const l of [-3, 0, 0.25, 2.7, 4.5, 9]) {
      expect(dayToLogical(dailyDays, logicalToDay(dailyDays, l)!)).toBeCloseTo(l, 9);
    }
  });

  it("aligns the same date across daily and weekly charts", () => {
    // Daily bar 5 (Mon 8 Jan) must land exactly on weekly bar 1 (week of 8 Jan).
    expect(dayToLogical(weeklyDays, logicalToDay(dailyDays, 5)!)).toBe(1);
  });

  it("handles empty input", () => {
    expect(logicalToDay([], 1)).toBeNull();
    expect(dayToLogical([], 1)).toBeNull();
  });
});
