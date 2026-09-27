import pandas as pd
import pytest

from kaching.indicators import atr, build_indicators, ema, keltner, to_weekly


def bars(closes, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100})


def test_ema_matches_hand_computation():
    s = pd.Series([1.0, 2.0, 3.0])
    # span=3 -> alpha=0.5: 1, 1.5, 2.25
    assert ema(s, 3).tolist() == [1.0, 1.5, 2.25]


def test_atr_uses_wilder_smoothing():
    df = bars([10, 10, 13])
    # TR: 2 (first bar H-L), 2, max(2, |14-10|, |12-10|)=4 ; RMA alpha=1/2: 2, 2, 3
    assert atr(df, 2).tolist() == [2.0, 2.0, 3.0]


def test_keltner_bands_symmetric_around_mid():
    df = bars(list(range(1, 40)))
    kc = keltner(df)
    assert ((kc["upper"] - kc["mid"]) - (kc["mid"] - kc["lower"])).abs().max() < 1e-9
    assert (kc["upper"] > kc["lower"]).all()


def test_to_weekly_ends_friday_and_aggregates():
    df = bars([1, 2, 3, 4, 5, 6, 7], start="2024-01-01")  # Mon 1st .. Tue 9th
    w = to_weekly(df)
    assert list(w.index.day_name()) == ["Friday", "Friday"]
    first = w.iloc[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (1, 6, 0, 5, 500)
    assert w.iloc[1]["close"] == 7  # partial current week uses latest close


def test_weekly_values_align_to_daily_index():
    df = bars(list(range(1, 30)))
    ind = build_indicators(df)
    w = ind["W EMA 21"]
    assert w.index.equals(df.index)
    assert not w.isna().any()
    # constant within a week
    week = df.index.to_period("W-FRI")
    assert (w.groupby(week).nunique() == 1).all()
    assert ind["W EMA 21"].iloc[-1] == pytest.approx(ema(to_weekly(df)["close"], 21).iloc[-1])
