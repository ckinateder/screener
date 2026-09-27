"""SQLite storage for daily bars. One DB for the whole app, keyed by (ticker, date)."""
import os
import sqlite3
from pathlib import Path

import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, date)
)
"""


def db_path() -> Path:
    return Path(os.environ.get("KACHING_DB", "data/kaching.db"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def upsert_bars(conn: sqlite3.Connection, ticker: str, bars: pd.DataFrame) -> int:
    """Insert/replace bars (DatetimeIndex, lowercase OHLCV columns). Returns row count."""
    if bars.empty:
        return 0
    rows = [
        (ticker, idx.strftime("%Y-%m-%d"), *(float(r[c]) for c in COLUMNS[:-1]), int(r["volume"]))
        for idx, r in bars[COLUMNS].iterrows()
    ]
    with conn:
        conn.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_bars(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM bars WHERE ticker = ? ORDER BY date",
        conn,
        params=(ticker,),
        parse_dates=["date"],
        index_col="date",
    )
    return df


def date_range(conn: sqlite3.Connection, ticker: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    lo, hi = conn.execute("SELECT MIN(date), MAX(date) FROM bars WHERE ticker = ?", (ticker,)).fetchone()
    return None if lo is None else (pd.Timestamp(lo), pd.Timestamp(hi))


def delete_ticker(conn: sqlite3.Connection, ticker: str) -> None:
    with conn:
        conn.execute("DELETE FROM bars WHERE ticker = ?", (ticker,))


def list_tickers(conn: sqlite3.Connection) -> list[tuple[str, str, str, int]]:
    return conn.execute(
        "SELECT ticker, MIN(date), MAX(date), COUNT(*) FROM bars GROUP BY ticker ORDER BY ticker"
    ).fetchall()
