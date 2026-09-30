"""EMA / ATR / Keltner indicators, plus daily -> weekly resampling."""
import pandas as pd

from kaching.support import support_zones

# The fixed kaching indicator set. Users can edit params/style/visibility, but not add or remove entries.
DEFAULT_CONFIG: list[dict] = [
    {"id": "d_ema_9", "kind": "ema", "tf": "D", "length": 9, "color": "#facc15", "width": 2, "visible": True},
    {"id": "d_ema_21", "kind": "ema", "tf": "D", "length": 21, "color": "#22d3ee", "width": 2, "visible": True},
    {"id": "d_sma_50", "kind": "sma", "tf": "D", "length": 50, "color": "#fb923c", "width": 2, "visible": True},
    {"id": "d_sma_100", "kind": "sma", "tf": "D", "length": 100, "color": "#e879f9", "width": 2, "visible": True},
    {"id": "w_ema_21", "kind": "ema", "tf": "W", "length": 21, "color": "#0891b2", "width": 2, "visible": False},
    {"id": "w_sma_50", "kind": "sma", "tf": "W", "length": 50, "color": "#c2410c", "width": 2, "visible": False},
    {"id": "w_sma_100", "kind": "sma", "tf": "W", "length": 100, "color": "#a21caf", "width": 2, "visible": False},
    {"id": "d_kc", "kind": "kc", "tf": "D", "ema_length": 20, "atr_length": 10, "multiplier": 2.0,
     "color": "#a3e635", "width": 1, "visible": True},
    {"id": "w_kc", "kind": "kc", "tf": "W", "ema_length": 20, "atr_length": 10, "multiplier": 2.0,
     "color": "#94a3b8", "width": 1, "visible": True},
    # Support zones ("sr"): drawn as bands, not line series; see kaching/support.py.
    {"id": "d_sr", "kind": "sr", "tf": "D", "pivot": 5, "tolerance": 1.0, "lookback_years": 3, "max_zones": 3,
     "min_touches": 2, "color": "#f472b6", "width": 1, "visible": False},
    {"id": "w_sr", "kind": "sr", "tf": "W", "pivot": 2, "tolerance": 2.0, "lookback_years": 3, "max_zones": 3,
     "min_touches": 1, "color": "#38bdf8", "width": 1, "visible": True},
]

LINE_KINDS = ("ema", "sma", "kc")

# Indicators replaced by another kind; saved configs are migrated (keeping style/visibility).
RENAMED_IDS = {"d_ema_50": "d_sma_50", "d_ema_100": "d_sma_100", "w_ema_50": "w_sma_50", "w_ema_100": "w_sma_100"}


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()  # NaN until n bars exist


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Average True Range with Wilder (RMA) smoothing, matching TradingView's ta.atr."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / n, adjust=False).mean()


def keltner(df: pd.DataFrame, ema_n: int = 20, atr_n: int = 10, mult: float = 2.0) -> dict[str, pd.Series]:
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


def _compute(bars: pd.DataFrame, cfg: dict) -> dict[str, pd.Series]:
    if cfg["kind"] == "ema":
        return {cfg["id"]: ema(bars["close"], cfg["length"])}
    if cfg["kind"] == "sma":
        return {cfg["id"]: sma(bars["close"], cfg["length"])}
    kc = keltner(bars, cfg["ema_length"], cfg["atr_length"], cfg["multiplier"])
    return {f"{cfg['id']}:{part}": s for part, s in kc.items()}


def build_indicators(daily: pd.DataFrame, config: list[dict] = DEFAULT_CONFIG, tf: str = "D") -> dict[str, pd.Series]:
    """Indicator series keyed by id (Keltner parts as '<id>:upper|mid|lower').

    tf="D": aligned to the daily index; weekly indicators are mapped onto their days.
    tf="W": weekly indicators only, on the weekly (W-FRI) index.
    """
    weekly = to_weekly(daily)
    out: dict[str, pd.Series] = {}
    for cfg in config:
        if cfg["kind"] not in LINE_KINDS:
            continue
        if cfg["tf"] == "D" and tf == "D":
            out.update(_compute(daily, cfg))
        elif cfg["tf"] == "W":
            for key, s in _compute(weekly, cfg).items():
                out[key] = s if tf == "W" else _weekly_to_daily(s, daily.index)
    return out


def build_zones(daily: pd.DataFrame, config: list[dict], tf: str = "D") -> dict[str, list[dict]]:
    """Support zones per "sr" entry: weekly entries use weekly bars; the W chart gets weekly only."""
    weekly = to_weekly(daily)
    out = {}
    for cfg in config:
        if cfg["kind"] != "sr" or (tf == "W" and cfg["tf"] == "D"):
            continue
        out[cfg["id"]] = support_zones(
            weekly if cfg["tf"] == "W" else daily, cfg["pivot"], cfg["tolerance"],
            cfg["lookback_years"], cfg["max_zones"], cfg["min_touches"],
        )
    return out
