"""EMA / ATR / Keltner indicators, plus daily -> weekly resampling."""
import pandas as pd

KELTNER_EMA = 20
KELTNER_ATR = 10
KELTNER_MULT = 2.0

DAILY_EMAS = (9, 21, 50, 100)
WEEKLY_EMAS = (21, 50, 100)


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Average True Range with Wilder (RMA) smoothing, matching TradingView's ta.atr."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / n, adjust=False).mean()


def keltner(df: pd.DataFrame, ema_n=KELTNER_EMA, atr_n=KELTNER_ATR, mult=KELTNER_MULT) -> dict[str, pd.Series]:
    mid = ema(df["close"], ema_n)
    band = mult * atr(df, atr_n)
    return {"mid": mid, "upper": mid + band, "lower": mid - band}


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily bars into weeks ending Friday; weeks with no trading days are dropped."""
    weekly = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return weekly.dropna(subset=["close"])


def _weekly_to_daily(weekly_series: pd.Series, daily_index: pd.DatetimeIndex) -> pd.Series:
    # Each daily bar takes the value of the week it belongs to (W-FRI label = that week's Friday).
    week_label = daily_index.to_period("W-FRI").end_time.normalize()
    return pd.Series(weekly_series.reindex(week_label).to_numpy(), index=daily_index)


def build_indicators(daily: pd.DataFrame) -> dict[str, pd.Series]:
    """All chart indicators, aligned to the daily index. Keys are display names."""
    out: dict[str, pd.Series] = {}
    for n in DAILY_EMAS:
        out[f"D EMA {n}"] = ema(daily["close"], n)
    for part, s in keltner(daily).items():
        out[f"D KC {part}"] = s

    weekly = to_weekly(daily)
    for n in WEEKLY_EMAS:
        out[f"W EMA {n}"] = _weekly_to_daily(ema(weekly["close"], n), daily.index)
    for part, s in keltner(weekly).items():
        out[f"W KC {part}"] = _weekly_to_daily(s, daily.index)
    return out
