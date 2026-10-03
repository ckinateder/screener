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
# Yahoo sometimes returns no expirations for a stock that has options (seen for PFE). Empty results are
# rechecked hourly instead of trusted for a day, and never overwrite a list we already had.
EMPTY_TTL = timedelta(hours=1)


def fetch_market_info(ticker: str) -> dict:
    """Live from Yahoo. Module-level so tests can monkeypatch it. Raises on network errors."""
    t = yf.Ticker(ticker)
    expirations = list(t.options)  # empty for symbols without listed options (e.g. mutual funds)
    if not expirations:  # one retry: an empty list is sometimes a transient Yahoo glitch
        expirations = list(yf.Ticker(ticker).options)
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
    try:  # classification, for the sector ETF suggestion (Chart Checklist #10)
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
    ttl = CACHE_TTL if cached and cached["expirations"] else EMPTY_TTL
    if (cached and not force and cached.get("quote_type") is not None
            and now - datetime.fromisoformat(cached["fetched_at"]) < ttl):
        return cached
    try:
        fresh = fetch_market_info(ticker)
    except Exception:
        return cached
    if not fresh["expirations"] and cached and cached["expirations"]:
        fresh = {**fresh, "expirations": cached["expirations"]}  # don't let a glitch erase known expirations
    fresh = {**fresh, "fetched_at": now.isoformat()}
    db.put_market_info(conn, ticker, fresh)
    return fresh
