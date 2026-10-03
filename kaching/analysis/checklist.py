"""The 60-second Chart Checklist (strategy-rules.md), measured.

Each check reports the measured value, its threshold, and passed: True / False / None, where None means
not applicable (e.g. too little history, or no volume data for mutual funds) and isn't counted.
"Graded" checks also get a 0-100 score: 100 exactly when the check passes, falling off below the threshold
(curves below); the chart score is their average. "Gate" checks are must-haves, pass/fail only.
The checklist uses the strategy's own parameters below, independent of the chart's display settings.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from kaching.indicators import atr, ema, keltner, sma, to_weekly
from kaching.support import support_zones, swing_highs, swing_lows

EVAL_YEARS = 3  # only recent history matters; keeps full-history tickers fast

W_PIVOT, W_LOOKBACK_YEARS = 2, 1        # 1. weekly trend: swings over the last 1 year
D_PIVOT, D_LOOKBACK_BARS = 5, 126       # 2. daily trend: swings over the last ~6 months
RECENT_BARS = 63                        # 3. ~90 calendar days
EMA_LEN, EMA_WINDOW, EMA_MIN_PCT = 21, 20, 80.0           # 4.
SMA_LEN, ATR_LEN, SMA_MIN_ATR = 50, 14, 1.0               # 5. "room to spare" = 1 ATR
KC_EMA, KC_ATR, KC_MULT = 20, 10, 2.0                     # 6.
KC_WINDOW, KC_MIN, KC_MAX = 5, 0.5, 1.1
VOL_WINDOW, VOL_MIN_RATIO = 50, 1.0                       # 7.
PRICE_MIN, PRICE_MAX = 25.0, 300.0                        # 11. (gate) sweet spot for spread math
SUPPORT_MIN_ZONES = 2                                     # 8. weekly zones, W Support defaults:
SUPPORT_PIVOT, SUPPORT_TOL, SUPPORT_YEARS, SUPPORT_MIN_TOUCHES = 2, 2.0, 3, 1
ZONE_CAP = 10  # zones counted at most (shown as "10+")
# 9. Vertical = a big move (absolute %, the rule is about spread math in dollars) made in a near-straight
# line. Size alone flags volatile stocks in ordinary choppy months (SNDK: median 20d gain ~20%).
VERTICAL_BARS, VERTICAL_MIN_GAIN, VERTICAL_MIN_ER = 20, 0.15, 0.4
AVG_VOL_WINDOW, AVG_VOL_MIN = 50, 1_000_000               # 12. (gate)
WEEKLY_OPTION_WEEKS = 4                                   # 13. (gate) an expiration in each of the next 4 weeks
EARNINGS_WINDOW_DAYS = 42                                 # 14. (gate) earnings must be > 6 weeks away
SECTOR_TREND_CHECKS = ("weekly_trend", "daily_sync", "recent_90d")  # 10. the ETF must pass these
RS_BARS = 63                                                       # 10. relative strength vs SPY, ~3 months
TRADING_DAYS_PER_MONTH = 21

# Must-have items: pass/fail only, reported separately from the chart score and listed last (11-14).
GATES = {"price_range", "avg_volume", "weekly_options", "earnings"}

# Score curves (graded checks): linear from 0 at the first value to full marks at the second.
# "Moderate" calibration: score 50 one threshold-width below the pass line, 0 two widths below.
TREND_DROP = (-0.05, 0.0)       # 1/2/10: a lower high (or low) scores its half 50 at -2.5%, 0 at -5%
TREND_BROKEN_CAP = 0.40         #        below the last swing low: always a fail
RECENT_RETURN = (-0.10, 0.0)    # 3: 63-day return (half the score)
RECENT_SLOPE = (-0.03, 0.0)     # 3: regression slope, per month (other half)
EMA_PCT = (40.0, EMA_MIN_PCT)   # 4: % of last 20 closes above; below the EMA now caps at 0.49
SMA_ATRS = (-1.0, SMA_MIN_ATR)  # 5: ATRs above the 50 MA
KC_BELOW = (-0.5, KC_MIN)       # 6: position below the band
KC_ABOVE = (1.7, KC_MAX)        # 6: position above the band (descending)
VOL_RATIO = (0.6, VOL_MIN_RATIO)  # 7: up/down volume ratio
VERTICAL_FADE = (VERTICAL_MIN_GAIN, 0.30)  # 9: vertical runs score 0.40 -> 0 as the gain grows


# ------------------------------------------------------------------ building blocks

def trend(bars: pd.DataFrame, pivot: int) -> dict | None:
    """Higher-high / higher-low test on the last two swing highs and lows.

    Returns None when there are fewer than two of either (no trend structure to judge).
    "up" also requires the close to hold above the last swing low (trend not broken).
    """
    highs, lows = swing_highs(bars, pivot), swing_lows(bars, pivot)
    if len(highs) < 2 or len(lows) < 2:
        return None
    (_, h1), (_, h2) = highs[-2:]
    (_, l1), (_, l2) = lows[-2:]
    close = float(bars["close"].iloc[-1])
    return {"up": bool(h2 > h1 and l2 > l1 and close > l2), "highs": (h1, h2), "lows": (l1, l2),
            "broken": close <= l2}


def pct_above(close: pd.Series, line: pd.Series, n: int) -> float:
    """% of the last n closes strictly above `line`."""
    return float((close.iloc[-n:] > line.iloc[-n:]).mean() * 100)


def keltner_position(close: pd.Series, mid: pd.Series, upper: pd.Series, n: int) -> float:
    """Average over the last n bars of (close - mid) / (upper - mid): 0 = mid line, 1 = upper band."""
    width = (upper - mid).iloc[-n:]
    return float(((close.iloc[-n:] - mid.iloc[-n:]) / width.where(width > 0)).mean())


def up_down_volume_ratio(close: pd.Series, volume: pd.Series, n: int) -> float | None:
    """Volume on up days / volume on down days over the last n bars. None without volume data."""
    change = close.diff().iloc[-n:]
    vol = volume.iloc[-n:]
    up, down = vol[change > 0].sum(), vol[change < 0].sum()
    if up + down == 0:
        return None
    return float("inf") if down == 0 else float(up / down)


def efficiency_ratio(close: pd.Series, n: int) -> float:
    """Straightness of the last n bars: |net move| / sum of |daily moves|. 1 = straight line, ~0 = choppy."""
    window = close.iloc[-(n + 1):]
    path = float(window.diff().abs().sum())
    return abs(float(window.iloc[-1] - window.iloc[0])) / path if path > 0 else 0.0


def regression_slope(close: pd.Series) -> float:
    """Least-squares slope of log(close) per bar (positive = trending up)."""
    return float(np.polyfit(np.arange(len(close)), np.log(close.to_numpy()), 1)[0])


# ------------------------------------------------------------------ scores (0-1; see curves above)

def ramp(x: float, zero: float, full: float) -> float:
    """0 at `zero`, 1 at `full`, linear between, clipped to [0, 1]. Works for descending curves too."""
    return float(min(1.0, max(0.0, (x - zero) / (full - zero))))


def score_trend(t: dict | None) -> float:
    if t is None:
        return 0.0
    (h1, h2), (l1, l2) = t["highs"], t["lows"]
    s = (ramp(h2 / h1 - 1, *TREND_DROP) + ramp(l2 / l1 - 1, *TREND_DROP)) / 2
    return min(s, TREND_BROKEN_CAP) if t["broken"] else s


def score_recent(ret: float, monthly_slope: float) -> float:
    return (ramp(ret, *RECENT_RETURN) + ramp(monthly_slope, *RECENT_SLOPE)) / 2


def score_ema(pct: float, dist: float) -> float:
    s = ramp(pct, *EMA_PCT)
    return s if dist > 0 else min(s, 0.49)


def score_sma(atrs: float) -> float:
    return ramp(atrs, *SMA_ATRS)


def score_keltner(pos: float) -> float:
    if pos < KC_MIN:
        return ramp(pos, *KC_BELOW)
    if pos > KC_MAX:
        return ramp(pos, *KC_ABOVE)
    return 1.0


def score_volume(ratio: float) -> float:
    return ramp(ratio, *VOL_RATIO)


def score_support(zones: int) -> float:
    return min(zones / SUPPORT_MIN_ZONES, 1.0)


def chart_score(scores: list[int]) -> int | None:
    """The chart score: the average of the graded checks' scores."""
    return round(sum(scores) / len(scores)) if scores else None


def score_vertical(gain: float, vertical: bool) -> float:
    return 0.40 * (1 - ramp(gain, *VERTICAL_FADE)) if vertical else 1.0


# ------------------------------------------------------------------ checklist

def _check(check_id: str, label: str, value: str, threshold: str, passed: bool | None) -> dict:
    """A gate (must-have): pass/fail only."""
    return {"id": check_id, "label": label, "value": value, "threshold": threshold, "passed": passed,
            "score": None, "kind": "gate" if check_id in GATES else "graded"}


def _graded(check_id: str, label: str, value: str, threshold: str, passed: bool | None,
            raw: float | None) -> dict:
    """A graded check. Score 100 exactly when it passes; a failing check never shows 100."""
    check = _check(check_id, label, value, threshold, passed)
    if passed is not None and raw is not None:
        check["score"] = 100 if passed else min(99, round(raw * 100))
    return check


def _trend_text(t: dict | None) -> str:
    if t is None:
        return "not enough swings"
    (h1, h2), (l1, l2) = t["highs"], t["lows"]
    text = f"HH {h2:.2f} {'>' if h2 > h1 else '≤'} {h1:.2f} · HL {l2:.2f} {'>' if l2 > l1 else '≤'} {l1:.2f}"
    return text + (" · below last swing low" if t["broken"] else "")


def _week_starts(today: date, weeks: int) -> list[date]:
    """Mondays of the next `weeks` weeks: this week on a weekday, next week on a weekend (Sunday routine)."""
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:
        monday += timedelta(days=7)
    return [monday + timedelta(weeks=i) for i in range(weeks)]


def _weekly_options_check(expirations: list[str], today: date) -> dict:
    rule = f"an expiration in each of the next {WEEKLY_OPTION_WEEKS} weeks"
    if not expirations:
        return _check("weekly_options", "Weekly expirations available", "no listed options", rule, False)
    dates = sorted(d for d in (date.fromisoformat(e) for e in expirations) if d >= today)
    weeks = _week_starts(today, WEEKLY_OPTION_WEEKS)
    covered = sum(any(w <= d < w + timedelta(days=7) for d in dates) for w in weeks)
    upcoming = ", ".join(d.strftime("%m-%d") for d in dates[:3])
    if covered == WEEKLY_OPTION_WEEKS:
        value = f"weekly · next {upcoming}"
    else:
        value = f"{covered}/{WEEKLY_OPTION_WEEKS} weeks covered · next {upcoming}"
    return _check("weekly_options", "Weekly expirations available", value, rule, covered == WEEKLY_OPTION_WEEKS)


def _earnings_check(earnings: str | None, today: date) -> dict:
    rule = f"next earnings more than {EARNINGS_WINDOW_DAYS // 7} weeks ({EARNINGS_WINDOW_DAYS} days) away"
    label = "Earnings outside trade window"
    if earnings is None:
        return _check("earnings", label, "no earnings date", rule, None)
    when = date.fromisoformat(earnings)
    days = (when - today).days
    if days < 0:  # Yahoo hasn't published the next date yet
        return _check("earnings", label, f"last reported {when:%b %-d}; next not announced", rule, None)
    return _check("earnings", label, f"{when:%b %-d} (in {days} days)", rule, days > EARNINGS_WINDOW_DAYS)


def _sector_check(sector: dict | None) -> dict:
    """#10: the sector ETF passes the trend checks (#1-#3); relative strength vs SPY shown for info."""
    label, rule = "Sector ETF trending same direction", "sector ETF passes checks 1–3 (trend)"
    if sector is None:
        return _graded("sector_etf", label, "no sector ETF", rule, None, None)
    etf = {c["id"]: c for c in run_checklist(sector["bars"])["checks"]}
    results = [etf[c]["passed"] for c in SECTOR_TREND_CHECKS]
    marks = "".join({True: "✓", False: "✗", None: "–"}[r] for r in results)
    value = f"{sector['etf']} ({sector['source']}) · trend {marks}"
    etf_close, spy_close = sector["bars"]["close"], sector["spy_bars"]["close"]
    if len(etf_close) > RS_BARS and len(spy_close) > RS_BARS:
        rs = (etf_close.iloc[-1] / etf_close.iloc[-(RS_BARS + 1)]) - (spy_close.iloc[-1] / spy_close.iloc[-(RS_BARS + 1)])
        value += f" · {rs:+.1%} vs SPY (3 mo)"
    passed = None if None in results else all(results)
    raw = None if passed is None else sum(etf[c]["score"] for c in SECTOR_TREND_CHECKS) / 300
    return _graded("sector_etf", label, value, rule, passed, raw)


def run_checklist(daily: pd.DataFrame, info: dict | None = None, today: date | None = None,
                  sector: dict | None = None) -> dict:
    """Run all 14 checks on daily bars (oldest first). See the module docstring for the result shape.

    `info` is market data from kaching.market_info ({expirations, earnings}); without it, #13/#14 are n/a.
    `sector` is {etf, source, bars, spy_bars} for the stock's sector ETF; without it, #10 is n/a.
    """
    today = today or date.today()
    if len(daily) > 0:
        daily = daily[daily.index >= daily.index[-1] - pd.DateOffset(years=EVAL_YEARS)]
    close, n = daily["close"], len(daily)
    checks = []

    # 1. Weekly trend direction
    weekly_all = to_weekly(daily) if n else daily  # #8 searches all EVAL_YEARS; #1 only the last year
    weekly = weekly_all
    if len(weekly):
        weekly = weekly[weekly.index >= weekly.index[-1] - pd.DateOffset(years=W_LOOKBACK_YEARS)]
    w = trend(weekly, W_PIVOT) if len(weekly) >= 2 * W_PIVOT + 1 else None
    w_enough = len(weekly) >= 26  # half a year of weeks before "no swings" counts as a fail
    checks.append(_graded("weekly_trend", "Weekly trend direction",
                          _trend_text(w) if w_enough else "not enough history",
                          "higher high and higher low, close above last swing low",
                          (w is not None and w["up"]) if w_enough else None, score_trend(w)))

    # 2. Daily trend in sync with weekly
    d = trend(daily.iloc[-D_LOOKBACK_BARS:], D_PIVOT) if n >= D_LOOKBACK_BARS else None
    w_up, d_up = (w is not None and w["up"]), (d is not None and d["up"])
    checks.append(_graded("daily_sync", "Daily trend in sync with weekly",
                          f"W {'up' if w_up else 'not up'} · D {'up' if d_up else 'not up'}" if n >= D_LOOKBACK_BARS
                          else "not enough history",
                          "both timeframes up",
                          (w_up and d_up) if n >= D_LOOKBACK_BARS and w_enough else None,
                          (score_trend(w) + score_trend(d)) / 2))

    # 3. Last 90 days on the daily
    if n > RECENT_BARS:
        recent = close.iloc[-(RECENT_BARS + 1):]
        ret = float(recent.iloc[-1] / recent.iloc[0] - 1)
        slope = regression_slope(recent)
        monthly = float(np.exp(slope * TRADING_DAYS_PER_MONTH) - 1)
        checks.append(_graded("recent_90d", "Last 90 days on the daily",
                              f"{ret:+.1%} · slope {monthly:+.1%}/mo", "return > 0 and slope > 0",
                              ret > 0 and slope > 0, score_recent(ret, monthly)))
    else:
        checks.append(_check("recent_90d", "Last 90 days on the daily", "not enough history",
                             "return > 0 and slope > 0", None))

    # 4. Price vs. 21 EMA
    if n >= EMA_LEN + EMA_WINDOW:
        line = ema(close, EMA_LEN)
        pct, dist = pct_above(close, line, EMA_WINDOW), float(close.iloc[-1] / line.iloc[-1] - 1)
        checks.append(_graded("ema21", "Price vs. 21 EMA", f"{pct:.0f}% of {EMA_WINDOW}d · now {dist:+.1%}",
                              f"≥ {EMA_MIN_PCT:.0f}% of last {EMA_WINDOW} closes above, and above now",
                              pct >= EMA_MIN_PCT and dist > 0, score_ema(pct, dist)))
    else:
        checks.append(_check("ema21", "Price vs. 21 EMA", "not enough history",
                             f"≥ {EMA_MIN_PCT:.0f}% of last {EMA_WINDOW} closes above, and above now", None))

    # 5. Price vs. 50 MA, with room to spare
    if n >= SMA_LEN:
        line = sma(close, SMA_LEN)
        gap = float(close.iloc[-1] - line.iloc[-1])
        unit = float(atr(daily, ATR_LEN).iloc[-1])
        atrs = gap / unit if unit > 0 else 0.0
        checks.append(_graded("sma50", "Price vs. 50 MA", f"{gap / line.iloc[-1]:+.1%} ({atrs:.1f} ATR)",
                              f"above by ≥ {SMA_MIN_ATR:g} ATR({ATR_LEN})", atrs >= SMA_MIN_ATR, score_sma(atrs)))
    else:
        checks.append(_check("sma50", "Price vs. 50 MA", "not enough history",
                             f"above by ≥ {SMA_MIN_ATR:g} ATR({ATR_LEN})", None))

    # 6. Keltner Channel position
    if n >= KC_EMA + KC_WINDOW:
        kc = keltner(daily, KC_EMA, KC_ATR, KC_MULT)
        pos = keltner_position(close, kc["mid"], kc["upper"], KC_WINDOW)
        checks.append(_graded("keltner", "Keltner Channel position", f"{pos:.2f} (0 = mid, 1 = upper band)",
                              f"{KC_MIN:g}–{KC_MAX:g} avg over {KC_WINDOW}d", KC_MIN <= pos <= KC_MAX,
                              score_keltner(pos)))
    else:
        checks.append(_check("keltner", "Keltner Channel position", "not enough history",
                             f"{KC_MIN:g}–{KC_MAX:g} avg over {KC_WINDOW}d", None))

    # 7. Volume on up vs. down moves
    ratio = up_down_volume_ratio(close, daily["volume"], VOL_WINDOW) if n > VOL_WINDOW else None
    if n <= VOL_WINDOW:
        value = "not enough history"
    elif ratio is None:
        value = "no volume data"
    else:
        value = "all up days" if ratio == float("inf") else f"{ratio:.2f}× up/down"
    checks.append(_graded("volume", "Volume on up vs. down moves", value,
                          f"up-day ÷ down-day volume ≥ {VOL_MIN_RATIO:g} over {VOL_WINDOW}d",
                          None if ratio is None else ratio >= VOL_MIN_RATIO,
                          None if ratio is None else score_volume(min(ratio, 10.0))))

    # 11. Stock price in range (gate)
    last = float(close.iloc[-1]) if n else None
    checks.append(_check("price_range", "Stock price in range",
                         f"${last:,.2f}" if last is not None else "no data",
                         f"${PRICE_MIN:g}–${PRICE_MAX:g}",
                         PRICE_MIN <= last <= PRICE_MAX if last is not None else None))

    # 8. Support layers (the "steady uptrend" half of this rule is check 1)
    if w_enough:
        zones = support_zones(weekly_all, SUPPORT_PIVOT, SUPPORT_TOL, SUPPORT_YEARS, ZONE_CAP, SUPPORT_MIN_TOUCHES)
        levels = " · ".join(f"{(z['low'] + z['high']) / 2:.2f}" for z in zones[:3])  # nearest three
        count = f"{ZONE_CAP}+" if len(zones) == ZONE_CAP else str(len(zones))
        checks.append(_graded("support_layers", "Support layers below price",
                              f"{count} zones" + (f": {levels}" if levels else ""),
                              f"≥ {SUPPORT_MIN_ZONES} weekly support zones below price",
                              len(zones) >= SUPPORT_MIN_ZONES, score_support(len(zones))))
    else:
        checks.append(_check("support_layers", "Support layers below price", "not enough history",
                             f"≥ {SUPPORT_MIN_ZONES} weekly support zones below price", None))

    # 9. Not on a vertical straight-up run
    vertical_rule = (f"not (> {VERTICAL_MIN_GAIN:.0%} in {VERTICAL_BARS}d and straightness ≥ "
                     f"{VERTICAL_MIN_ER:g}); straightness 1 = straight line")
    if n > VERTICAL_BARS:
        gain = float(close.iloc[-1] / close.iloc[-(VERTICAL_BARS + 1)] - 1)
        er = efficiency_ratio(close, VERTICAL_BARS)
        vertical = gain > VERTICAL_MIN_GAIN and er >= VERTICAL_MIN_ER
        checks.append(_graded("not_vertical", "Not on a vertical run",
                              f"{gain:+.1%} in {VERTICAL_BARS}d · straightness {er:.2f}", vertical_rule,
                              not vertical, score_vertical(gain, vertical)))
    else:
        checks.append(_check("not_vertical", "Not on a vertical run", "not enough history", vertical_rule, None))

    # 12. Average daily volume (gate; n/a without volume data, e.g. mutual funds)
    avg_vol = float(daily["volume"].iloc[-AVG_VOL_WINDOW:].mean()) if n >= AVG_VOL_WINDOW else None
    if avg_vol is None:
        value = "not enough history"
    elif avg_vol == 0:
        value, avg_vol = "no volume data", None
    else:
        value = f"{avg_vol / 1e6:.2f}M shares/day"
    checks.append(_check("avg_volume", "Average daily volume", value,
                         f"≥ {AVG_VOL_MIN / 1e6:g}M over {AVG_VOL_WINDOW}d",
                         None if avg_vol is None else avg_vol >= AVG_VOL_MIN))

    # 13-14. Weekly expirations, earnings (gates; live market data, passed in by the caller)
    if info is None:
        checks.append(_check("weekly_options", "Weekly expirations available", "unavailable",
                             f"an expiration in each of the next {WEEKLY_OPTION_WEEKS} weeks", None))
        checks.append(_check("earnings", "Earnings outside trade window", "unavailable",
                             f"next earnings more than {EARNINGS_WINDOW_DAYS // 7} weeks away", None))
    else:
        checks.append(_weekly_options_check(info["expirations"], today))
        checks.append(_earnings_check(info["earnings"], today))

    # 10. Sector ETF trending the same direction
    checks.append(_sector_check(sector))

    # Display order: graded checks first (1-10), gates last (11-14).
    checks = [c for c in checks if c["kind"] == "graded"] + [c for c in checks if c["kind"] == "gate"]

    applicable = [c for c in checks if c["passed"] is not None]
    passed = sum(c["passed"] for c in applicable)
    graded = [c["score"] for c in checks if c["kind"] == "graded" and c["score"] is not None]
    gates = [c for c in checks if c["kind"] == "gate" and c["passed"] is not None]
    return {
        "as_of": daily.index[-1].strftime("%Y-%m-%d") if n else None,
        "passed": passed,
        "applicable": len(applicable),
        "all_pass": bool(applicable) and passed == len(applicable),
        "score": chart_score(graded),  # graded checks only
        "gates": {"passed": sum(c["passed"] for c in gates), "applicable": len(gates),
                  "failed": [c["label"] for c in gates if not c["passed"]]},
        "checks": checks,
    }
