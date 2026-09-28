import { describe, expect, it } from "vitest";
import { buildUrlSearch, readUrlState } from "./urlState";

describe("urlState", () => {
  it("reads and normalises symbol and tf", () => {
    expect(readUrlState("?symbol=aapl&tf=w")).toEqual({ symbol: "AAPL", tf: "W" });
  });

  it("drops missing or invalid values", () => {
    expect(readUrlState("")).toEqual({});
    expect(readUrlState("?symbol=%20&tf=M&layout=grid&sync=yes&tf2=X")).toEqual({});
  });

  it("reads the two-pane state", () => {
    expect(readUrlState("?symbol=NVDA&tf=D&symbol2=spy&tf2=W&layout=columns&sync=0")).toEqual({
      symbol: "NVDA", tf: "D", symbol2: "SPY", tf2: "W", layout: "columns", sync: false,
    });
  });

  it("round-trips a split layout", () => {
    const state = { symbol: "BRK-B", tf: "D" as const, symbol2: "SPY", tf2: "W" as const, layout: "rows" as const, sync: true };
    expect(readUrlState(buildUrlSearch(state))).toEqual(state);
  });

  it("keeps the right-edge lock in any layout, and only when on", () => {
    expect(buildUrlSearch({ symbol: "AAPL", tf: "D", layout: "single", lock: true })).toBe("?symbol=AAPL&tf=D&lock=1");
    expect(buildUrlSearch({ symbol: "AAPL", tf: "D", lock: false })).toBe("?symbol=AAPL&tf=D");
    expect(readUrlState("?symbol=AAPL&lock=1")).toEqual({ symbol: "AAPL", lock: true });
    expect(readUrlState("?symbol=AAPL&lock=0")).toEqual({ symbol: "AAPL" });
  });

  it("omits second-pane params in the single layout", () => {
    expect(buildUrlSearch({ symbol: "AAPL", tf: "D", symbol2: "SPY", tf2: "W", layout: "single", sync: true })).toBe(
      "?symbol=AAPL&tf=D",
    );
  });
});
