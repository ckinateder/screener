"""Incremental yfinance fetcher: only downloads dates not already in the DB."""
import math
import re
import sqlite3
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from kaching import db

EARLIEST_START = date(1900, 1, 1)  # "MAX": yfinance returns everything it has from here on
HEAL_TOLERANCE = 1e-4  # relative close difference that signals a split/dividend re-adjustment
_LOOKBACK_RE = re.compile(r"^(\d+)([DWMY])$", re.IGNORECASE)


def parse_lookback(value: str, today: date | None = None) -> date:
    """'MAX', '5Y', '6M', '2W', '30D' (relative to today) or 'YYYY-MM-DD' -> start date."""
    today = today or date.today()
    if value.strip().upper() == "MAX":
        return EARLIEST_START
    m = _LOOKBACK_RE.match(value.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2).upper()
        offset = {"D": pd.DateOffset(days=n), "W": pd.DateOffset(weeks=n),
                  "M": pd.DateOffset(months=n), "Y": pd.DateOffset(years=n)}[unit]
        return (pd.Timestamp(today) - offset).date()
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Invalid lookback {value!r}: use e.g. MAX, 5Y, 6M, 2W, 30D or YYYY-MM-DD") from None


def download(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Adjusted daily bars for [start, end) with a tz-naive DatetimeIndex and lowercase columns."""
    raw = yf.download(ticker, start=start, end=end, interval="1d",
                      auto_adjust=True, progress=False, threads=False)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=db.COLUMNS)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.lower() for c in raw.columns]
    raw.index = pd.DatetimeIndex(raw.index).tz_localize(None).normalize()
    return raw[db.COLUMNS].dropna(subset=["close"])


def _row_count(conn: sqlite3.Connection, ticker: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM bars WHERE ticker = ?", (ticker,)).fetchone()[0]


def fetch_ticker(conn: sqlite3.Connection, ticker: str, start: date, today: date | None = None) -> dict:
    """Bring `ticker` up to date from `start` to today. Returns a summary dict."""
    ticker = ticker.upper()
    end = (today or date.today()) + timedelta(days=1)  # yfinance `end` is exclusive
    before = _row_count(conn, ticker)
    healed = False

    stored = db.date_range(conn, ticker)
    if stored is None:
        db.upsert_bars(conn, ticker, download(ticker, start, end))
    else:
        lo, _ = stored
        # Anchor on the second-to-last stored bar: the last one may be a partial intraday bar
        # whose close legitimately changes, which must not trigger a heal.
        anchor_rows = conn.execute(
            "SELECT date, close FROM bars WHERE ticker = ? ORDER BY date DESC LIMIT 2", (ticker,)
        ).fetchall()
        anchor_date, anchor_close = pd.Timestamp(anchor_rows[-1][0]), anchor_rows[-1][1]

        recent = download(ticker, anchor_date.date(), end)
        if anchor_date in recent.index and not math.isclose(
            recent.at[anchor_date, "close"], anchor_close, rel_tol=HEAL_TOLERANCE
        ):
            healed = True
            db.delete_ticker(conn, ticker)
            db.upsert_bars(conn, ticker, download(ticker, min(start, lo.date()), end))
        else:
            db.upsert_bars(conn, ticker, recent[recent.index > anchor_date])
            # Skip gaps with no weekdays (e.g. start on a Saturday) — yfinance warns on empty ranges.
            if len(pd.bdate_range(start, lo - pd.Timedelta(days=1))) > 0:
                db.upsert_bars(conn, ticker, download(ticker, start, lo.date()))

    return {
        "ticker": ticker,
        "new_rows": _row_count(conn, ticker) - before,
        "healed": healed,
        "range": db.date_range(conn, ticker),
    }
