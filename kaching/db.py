"""SQLite storage: daily bars keyed by (ticker, date), plus symbol metadata, watchlist and settings."""
import json
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
);
CREATE TABLE IF NOT EXISTS symbols (
    ticker       TEXT PRIMARY KEY,
    name         TEXT,
    exchange     TEXT,
    last_fetched TEXT,
    full_history INTEGER NOT NULL DEFAULT 0  -- 1 once all available history has been fetched
);
CREATE TABLE IF NOT EXISTS watchlist (
    ticker   TEXT PRIMARY KEY,
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("KACHING_DB", "data/kaching.db"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may open the connection (dependency) and use it (endpoint) on different threads.
    # Each connection still serves one request at a time, so disabling the check is safe.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a DB was created (CREATE TABLE IF NOT EXISTS won't)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(symbols)")}
    if "full_history" not in columns:
        with conn:
            conn.execute("ALTER TABLE symbols ADD COLUMN full_history INTEGER NOT NULL DEFAULT 0")


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


def last_two_closes(conn: sqlite3.Connection, ticker: str) -> list[float]:
    """Most recent close first."""
    rows = conn.execute(
        "SELECT close FROM bars WHERE ticker = ? ORDER BY date DESC LIMIT 2", (ticker,)
    ).fetchall()
    return [r[0] for r in rows]


def upsert_symbol(conn: sqlite3.Connection, ticker: str, name: str | None = None,
                  exchange: str | None = None, last_fetched: str | None = None) -> None:
    """Insert or update symbol metadata; None fields keep their existing value."""
    with conn:
        conn.execute(
            """INSERT INTO symbols (ticker, name, exchange, last_fetched) VALUES (?, ?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET
                 name = COALESCE(excluded.name, name),
                 exchange = COALESCE(excluded.exchange, exchange),
                 last_fetched = COALESCE(excluded.last_fetched, last_fetched)""",
            (ticker, name, exchange, last_fetched),
        )


def get_symbol(conn: sqlite3.Connection, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT ticker, name, exchange, last_fetched, full_history FROM symbols WHERE ticker = ?", (ticker,)
    ).fetchone()
    fields = ("ticker", "name", "exchange", "last_fetched", "full_history")
    return None if row is None else dict(zip(fields, row))


def mark_full_history(conn: sqlite3.Connection, ticker: str) -> None:
    with conn:
        conn.execute("UPDATE symbols SET full_history = 1 WHERE ticker = ?", (ticker,))


def get_watchlist(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT ticker FROM watchlist ORDER BY position")]


def set_watchlist(conn: sqlite3.Connection, tickers: list[str]) -> None:
    """Replace the whole watchlist with `tickers`, in order."""
    with conn:
        conn.execute("DELETE FROM watchlist")
        conn.executemany("INSERT INTO watchlist VALUES (?, ?)", [(t, i) for i, t in enumerate(tickers)])


def get_setting(conn: sqlite3.Connection, key: str):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else json.loads(row[0])


def put_setting(conn: sqlite3.Connection, key: str, value) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
