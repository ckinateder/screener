"""Option expirations and the next earnings date per ticker, from Yahoo, cached in SQLite for a day.

These change rarely, and the watchlist badges need them for every ticker, so each ticker costs one
Yahoo call per day at most.
"""
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone

import yfinance as yf

from kaching import db

CACHE_TTL = timedelta(hours=24)


def fetch_market_info(ticker: str) -> dict:
    """Live from Yahoo. Module-level so tests can monkeypatch it. Raises on network errors."""
    t = yf.Ticker(ticker)
    expirations = list(t.options)  # empty for symbols without listed options (e.g. mutual funds)
    earnings = None
    yf_log = logging.getLogger("yfinance")
    level = yf_log.level
    yf_log.setLevel(logging.CRITICAL)  # funds/ETFs have no calendar; yfinance logs an expected 404 for that
    try:
        dates = (t.calendar or {}).get("Earnings Date") or []
        earnings = dates[0].isoformat() if dates and isinstance(dates[0], date) else None
    except Exception:
        pass  # no fundamentals (funds, ETFs) -> unknown
    finally:
        yf_log.setLevel(level)
    try:  # classification, for the sector ETF suggestion (Chart Checklist #14)
        meta = t.info or {}
    except Exception:
        meta = {}
    return {"expirations": expirations, "earnings": earnings, "sector": meta.get("sector"),
            "industry": meta.get("industry"), "quote_type": meta.get("quoteType") or "UNKNOWN"}


def get_market_info(conn: sqlite3.Connection, ticker: str, force: bool = False,
                    now: datetime | None = None) -> dict | None:
    """{expirations, earnings, sector, industry, quote_type, fetched_at}; refetched after CACHE_TTL or forced.

    If Yahoo fails, serves whatever is cached (even stale); None when nothing is cached.
    """
    now = now or datetime.now(timezone.utc)
    cached = db.get_market_info(conn, ticker)
    # quote_type is NULL only in rows cached before classification was added: refetch those once.
    if (cached and not force and cached.get("quote_type") is not None
            and now - datetime.fromisoformat(cached["fetched_at"]) < CACHE_TTL):
        return cached
    try:
        fresh = fetch_market_info(ticker)
    except Exception:
        return cached
    fresh = {**fresh, "fetched_at": now.isoformat()}
    db.put_market_info(conn, ticker, fresh)
    return fresh
