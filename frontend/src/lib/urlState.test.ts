import { describe, expect, it } from "vitest";
import { buildUrlSearch, readUrlState } from "./urlState";

describe("urlState", () => {
  it("reads and normalises symbol and tf", () => {
    expect(readUrlState("?symbol=aapl&tf=w")).toEqual({ symbol: "AAPL", tf: "W" });
  });

  it("drops missing or invalid values", () => {
    expect(readUrlState("")).toEqual({});
    expect(readUrlState("?symbol=%20&tf=M")).toEqual({});
  });

  it("round-trips", () => {
    const state = { symbol: "BRK-B", tf: "D" as const };
    expect(readUrlState(buildUrlSearch(state))).toEqual(state);
  });
});
