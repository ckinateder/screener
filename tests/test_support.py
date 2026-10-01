import pandas as pd
import pytest

from kaching.support import support_zones, swing_highs, swing_lows


def bars_from_lows(lows, close=None, start="2024-01-01"):
    """Bars whose low follows `lows`; highs sit 1 above, close defaults to the last low + 0.5."""
    idx = pd.bdate_range(start, periods=len(lows))
    low = pd.Series(lows, index=idx, dtype=float)
    df = pd.DataFrame({"open": low + 0.5, "high": low + 1, "low": low, "close": low + 0.5, "volume": 100})
    if close is not None:
        df.iloc[-1, df.columns.get_loc("close")] = close
    return df


# A V at 90, a bounce, a second V at 90.5 (double bottom), then a rally to 120.
DOUBLE_BOTTOM = [100, 97, 94, 90, 94, 98, 101, 98, 94, 90.5, 95, 100, 105, 110, 115, 120, 121, 122]


def test_swing_lows_finds_both_bottoms():
    lows = swing_lows(bars_from_lows(DOUBLE_BOTTOM), pivot=2)
    assert [price for _, price in lows] == [90, 90.5]


def test_swing_highs_mirror_swing_lows():
    # highs sit 1 above lows in bars_from_lows: the peak at 101 (low) -> high 102
    highs = swing_highs(bars_from_lows(DOUBLE_BOTTOM), pivot=2)
    assert [price for _, price in highs] == [102]


def test_swing_lows_ignores_unconfirmed_recent_bars():
    # The last bar is the lowest, but there aren't `pivot` bars after it yet.
    lows = swing_lows(bars_from_lows([100, 99, 98, 97, 96, 95, 90]), pivot=2)
    assert lows == []


def test_flat_bottom_counts_once():
    lows = swing_lows(bars_from_lows([100, 95, 90, 90, 90, 95, 100]), pivot=2)
    assert [price for _, price in lows] == [90]


def test_double_bottom_is_one_zone_with_two_touches():
    zones = support_zones(bars_from_lows(DOUBLE_BOTTOM), pivot=2, tolerance_pct=2, lookback_years=3,
                          max_zones=3, min_touches=1)
    assert len(zones) == 1
    z = zones[0]
    assert (z["low"], z["high"], z["touches"]) == (90, 90.5, 2)
    assert z["first"] < z["last"]


def test_tolerance_splits_distant_lows():
    zones = support_zones(bars_from_lows(DOUBLE_BOTTOM), pivot=2, tolerance_pct=0.1, lookback_years=3,
                          max_zones=3, min_touches=1)
    assert [z["touches"] for z in zones] == [1, 1]


def test_single_touch_zone_keeps_its_true_price():
    zones = support_zones(bars_from_lows(DOUBLE_BOTTOM), pivot=2, tolerance_pct=0.1, lookback_years=3,
                          max_zones=3, min_touches=1)
    assert [(z["low"], z["high"]) for z in zones] == [(90.5, 90.5), (90, 90)]


def test_zones_above_price_are_excluded():
    zones = support_zones(bars_from_lows(DOUBLE_BOTTOM, close=85), pivot=2, tolerance_pct=2,
                          lookback_years=3, max_zones=3, min_touches=1)
    assert zones == []


def test_min_touches_filters_and_nearest_first():
    # Three separate bottoms at 80, 90 and 100, then a rally; 90 is hit twice.
    lows = [120, 115, 110, 100, 110, 120, 110, 90, 110, 120, 110, 90.3, 110, 120, 110, 80, 110, 130, 131, 132]
    bars = bars_from_lows(lows)
    zones = support_zones(bars, pivot=2, tolerance_pct=1, lookback_years=3, max_zones=3, min_touches=1)
    assert [round(z["low"]) for z in zones] == [100, 90, 80]  # nearest to price first
    zones = support_zones(bars, pivot=2, tolerance_pct=1, lookback_years=3, max_zones=3, min_touches=2)
    assert [(z["low"], z["high"], z["touches"]) for z in zones] == [(90, 90.3, 2)]
    zones = support_zones(bars, pivot=2, tolerance_pct=1, lookback_years=3, max_zones=2, min_touches=1)
    assert len(zones) == 2


def test_lookback_limits_history():
    lows = DOUBLE_BOTTOM + [122] * 600  # ~2.3 years of flat bars after the double bottom
    bars = bars_from_lows(lows)
    assert support_zones(bars, pivot=2, tolerance_pct=2, lookback_years=3, max_zones=3, min_touches=1)
    assert support_zones(bars, pivot=2, tolerance_pct=2, lookback_years=1, max_zones=3, min_touches=1) == []


@pytest.mark.parametrize("lows", [[], [100], [100, 99, 98]])
def test_short_input(lows):
    assert support_zones(bars_from_lows(lows), pivot=2, tolerance_pct=2, lookback_years=3,
                         max_zones=3, min_touches=1) == []
