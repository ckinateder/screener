import numpy as np
import pandas as pd
import pytest

from kaching.analysis.checklist import (
    efficiency_ratio,
    keltner_position,
    pct_above,
    regression_slope,
    run_checklist,
    trend,
    up_down_volume_ratio,
)


def daily_bars(closes, volume=None, spread=0.0075):
    """Daily bars from closes; high/low +/- `spread`, volume 2M on up days and 1M on down days by default."""
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2020-01-01", periods=len(closes))
    if volume is None:
        prev = np.concatenate([closes[:1], closes[:-1]])
        volume = np.where(closes >= prev, 2_000_000, 1_000_000)
    return pd.DataFrame({"open": closes, "high": closes * (1 + spread), "low": closes * (1 - spread),
                         "close": closes, "volume": volume}, index=idx)


def wavy_trend(n, drift, amplitude=0.05, period=40, start=100.0):
    """Exponential drift (per bar) with a sine wave on top, so there are pullbacks and swings."""
    i = np.arange(n)
    return start * np.exp(drift * i) * (1 + amplitude * np.sin(2 * np.pi * i / period))


def uptrend_then_climb():
    """~2.5 years of wavy uptrend, then 25 bars of steady climbing: should pass everything."""
    base = wavy_trend(620, drift=0.0015)
    climb = base[-1] * np.exp(0.0025 * np.arange(1, 26))
    return daily_bars(np.concatenate([base, climb]))


def by_id(result):
    return {c["id"]: c for c in result["checks"]}


# ------------------------------------------------------------------ helpers

def test_pct_above():
    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    line = pd.Series([2, 2, 2, 2, 2], dtype=float)
    assert pct_above(close, line, 4) == 75.0  # last 4: 2,3,4,5 vs 2 -> 3 strictly above


def test_keltner_position():
    close = pd.Series([12.0, 10.0])
    mid = pd.Series([10.0, 10.0])
    upper = pd.Series([12.0, 12.0])
    assert keltner_position(close, mid, upper, 1) == 0.0  # at the mid
    assert keltner_position(close, mid, upper, 2) == 0.5  # average of 1.0 and 0.0


def test_up_down_volume_ratio():
    close = pd.Series([10, 11, 10, 12], dtype=float)  # up, down, up
    volume = pd.Series([0, 300, 100, 300], dtype=float)
    assert up_down_volume_ratio(close, volume, 3) == 6.0  # (300 + 300) / 100
    assert up_down_volume_ratio(close, volume * 0, 3) is None  # no volume data (mutual funds)


def test_efficiency_ratio():
    assert efficiency_ratio(pd.Series([1.0, 2.0, 3.0, 4.0]), 3) == 1.0  # straight line
    assert efficiency_ratio(pd.Series([1.0, 3.0, 1.0, 3.0]), 3) == pytest.approx(2 / 6)  # net 2 over a 6-point path
    assert efficiency_ratio(pd.Series([5.0, 5.0, 5.0]), 2) == 0.0  # no movement at all


def test_regression_slope_sign():
    assert regression_slope(pd.Series(np.exp(0.01 * np.arange(30)))) > 0
    assert regression_slope(pd.Series(np.exp(-0.01 * np.arange(30)))) < 0


def test_trend_detects_up_and_down():
    up = daily_bars(wavy_trend(300, drift=0.002))
    down = daily_bars(wavy_trend(300, drift=-0.002))
    assert trend(up, pivot=5)["up"] is True
    assert trend(down, pivot=5)["up"] is False


def test_trend_needs_two_swings():
    assert trend(daily_bars(np.linspace(100, 200, 100)), pivot=5) is None  # straight line: no swings


# ------------------------------------------------------------------ full checklist

def test_clean_uptrend_passes_everything():
    result = run_checklist(uptrend_then_climb())
    failing = [(c["id"], c["value"]) for c in result["checks"] if c["passed"] is not True]
    assert failing == []
    assert (result["passed"], result["applicable"], result["all_pass"]) == (11, 11, True)


def test_downtrend_fails_trend_and_ma_checks():
    closes = uptrend_then_climb()["close"].to_numpy()[::-1]  # mirror in time -> downtrend
    checks = by_id(run_checklist(daily_bars(closes)))
    for check_id in ("weekly_trend", "daily_sync", "recent_90d", "ema21", "sma50", "keltner"):
        assert checks[check_id]["passed"] is False, check_id


def test_recent_decline_fails_90_day_check():
    base = uptrend_then_climb()["close"].to_numpy()
    decline = base[-1] * np.exp(-0.003 * np.arange(1, 64))
    checks = by_id(run_checklist(daily_bars(np.concatenate([base, decline]))))
    assert checks["recent_90d"]["passed"] is False
    assert checks["ema21"]["passed"] is False


def test_no_volume_makes_volume_checks_not_applicable():
    bars = uptrend_then_climb()
    bars["volume"] = 0
    result = run_checklist(bars)
    assert by_id(result)["volume"]["passed"] is None
    assert by_id(result)["avg_volume"]["passed"] is None
    assert result["applicable"] == 9 and result["all_pass"] is True


def test_short_history_reports_not_applicable_instead_of_crashing():
    result = run_checklist(daily_bars(wavy_trend(30, drift=0.002)))
    assert all(c["passed"] is None or isinstance(c["passed"], bool) for c in result["checks"])
    assert by_id(result)["sma50"]["passed"] is None  # needs 50 bars
    assert result["applicable"] < 11


def test_result_shape():
    result = run_checklist(uptrend_then_climb())
    assert result["as_of"] == uptrend_then_climb().index[-1].strftime("%Y-%m-%d")
    assert [c["id"] for c in result["checks"]] == [
        "weekly_trend", "daily_sync", "recent_90d", "ema21", "sma50", "keltner", "volume",
        "price_range", "support_layers", "not_vertical", "avg_volume"]
    for c in result["checks"]:
        assert set(c) == {"id", "label", "value", "threshold", "passed"}
        assert c["value"] and c["threshold"]


def test_empty_input():
    result = run_checklist(daily_bars([]))
    assert result["applicable"] == 0 and result["all_pass"] is False


def test_single_bar_only_judges_price():
    result = run_checklist(daily_bars([100.0]))
    assert [c["id"] for c in result["checks"] if c["passed"] is not None] == ["price_range"]


# ------------------------------------------------------------------ qualifying checks (#8-#11)

@pytest.mark.parametrize("scale,passed", [(1.0, True), (0.05, False), (2.0, False)])
def test_price_range(scale, passed):
    bars = uptrend_then_climb()  # ends around $270
    bars[["open", "high", "low", "close"]] *= scale
    assert by_id(run_checklist(bars))["price_range"]["passed"] is passed


def test_support_layers_need_two_zones_below_price():
    assert by_id(run_checklist(uptrend_then_climb()))["support_layers"]["passed"] is True
    smooth = daily_bars(100 * np.exp(0.001 * np.arange(700)))  # straight line: no swing lows at all
    check = by_id(run_checklist(smooth))["support_layers"]
    assert check["passed"] is False and check["value"].startswith("0 zones")


def test_trend_and_support_use_separate_windows():
    # Swings only in the older history, then a year of straight-line drift (no swings at all).
    base = uptrend_then_climb()["close"].to_numpy()
    drift = base[-1] * np.exp(0.0004 * np.arange(1, 261))
    checks = by_id(run_checklist(daily_bars(np.concatenate([base, drift]))))
    assert checks["weekly_trend"]["value"] == "not enough swings"  # trend looks at the last 1 year only
    assert checks["support_layers"]["passed"] is True              # support still searches 3 years


def test_big_but_choppy_month_is_not_vertical():
    # Like SNDK in Sep 2026: up >15% in 20 days, but zig-zagging (+6% / -4% days), not a straight line.
    base = uptrend_then_climb()["close"].to_numpy()
    steps = np.tile([1.06, 0.96], 10)
    choppy = base[-1] * np.cumprod(steps)
    check = by_id(run_checklist(daily_bars(np.concatenate([base, choppy]))))["not_vertical"]
    assert choppy[-1] / base[-1] - 1 > 0.15
    assert check["passed"] is True, check["value"]


def test_slow_steady_climber_is_not_vertical():
    # Regression: a fund-like steady climb with tiny daily moves. In ATR units it looked "vertical"
    # (FCNTX: +4.2 ATR on a +3.4% month); in % terms it's +3.7% vs the 50 MA.
    bars = daily_bars(100 * np.exp(0.0015 * np.arange(700)), spread=0.0, volume=0)
    assert by_id(run_checklist(bars))["not_vertical"]["passed"] is True


def test_vertical_run_fails():
    base = uptrend_then_climb()["close"].to_numpy()
    spike = base[-1] * np.exp(0.015 * np.arange(1, 21))  # +35% in 20 days
    check = by_id(run_checklist(daily_bars(np.concatenate([base, spike]))))["not_vertical"]
    assert check["passed"] is False


def test_avg_volume_threshold():
    bars = uptrend_then_climb()
    bars["volume"] = 900_000
    assert by_id(run_checklist(bars))["avg_volume"]["passed"] is False
    bars["volume"] = 1_200_000
    assert by_id(run_checklist(bars))["avg_volume"]["passed"] is True
