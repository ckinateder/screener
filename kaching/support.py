"""Automatic support zones: swing lows clustered by price, nearest below the current close."""
import pandas as pd


def swing_lows(bars: pd.DataFrame, pivot: int) -> list[tuple[pd.Timestamp, float]]:
    """(time, low) of bars lower than the `pivot` bars before and no higher than the `pivot` after.

    Strict on the left so a flat bottom counts once. The last `pivot` bars can't qualify yet:
    they need `pivot` later bars to confirm them.
    """
    lows = bars["low"].to_numpy()
    out = []
    for i in range(pivot, len(lows) - pivot):
        if lows[i] < lows[i - pivot:i].min() and lows[i] <= lows[i + 1:i + pivot + 1].min():
            out.append((bars.index[i], float(lows[i])))
    return out


def support_zones(bars: pd.DataFrame, pivot: int, tolerance_pct: float, lookback_years: int,
                  max_zones: int, min_touches: int) -> list[dict]:
    """Support zones below the latest close, nearest first.

    Swing lows from the last `lookback_years` are sorted by price and grouped whenever
    consecutive lows are within `tolerance_pct` of each other. Each zone is
    {low, high, touches, first, last} with the true touch prices (a single touch has low == high;
    the chart gives thin zones a minimum drawn height).
    """
    if len(bars) < 2 * pivot + 1:
        return []
    price = float(bars["close"].iloc[-1])
    window = bars[bars.index >= bars.index[-1] - pd.DateOffset(years=lookback_years)]

    clusters: list[list[tuple[pd.Timestamp, float]]] = []
    for time, low in sorted(swing_lows(window, pivot), key=lambda p: p[1]):
        if clusters and low - clusters[-1][-1][1] <= low * tolerance_pct / 100:
            clusters[-1].append((time, low))
        else:
            clusters.append([(time, low)])

    zones = []
    for cluster in clusters:
        prices = [p for _, p in cluster]
        times = [t for t, _ in cluster]
        low, high = min(prices), max(prices)
        if len(cluster) < min_touches or (low + high) / 2 >= price:
            continue
        zones.append({"low": low, "high": high, "touches": len(cluster), "first": min(times), "last": max(times)})

    zones.sort(key=lambda z: z["high"], reverse=True)  # nearest below price first
    return zones[:max_zones]
