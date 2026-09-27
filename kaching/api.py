"""FastAPI backend for the React app. Also serves the built frontend when present."""
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

import pandas as pd
import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from kaching import db
from kaching.fetcher import fetch_ticker, parse_lookback
from kaching.indicators import DEFAULT_CONFIG, build_indicators, to_weekly

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK = "5Y"
FETCH_THROTTLE = timedelta(minutes=5)
SEARCH_TYPES = {"EQUITY", "ETF", "INDEX"}
INDICATORS_KEY = "indicators"

app = FastAPI(title="Kaching")


def get_conn() -> Iterator[sqlite3.Connection]:
    # sqlite connections can't be shared across FastAPI's worker threads, so open one per request.
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def search_quotes(query: str, max_results: int = 15) -> list[dict]:
    """Raw Yahoo quote matches. Module-level so tests can monkeypatch it."""
    return yf.Search(query, max_results=max_results, news_count=0).quotes


# ---------------------------------------------------------------- models

class IndicatorSetting(BaseModel):
    id: str
    kind: Literal["ema", "kc"]
    tf: Literal["D", "W"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    width: int = Field(ge=1, le=4)
    visible: bool
    length: int | None = Field(default=None, ge=1, le=500)
    ema_length: int | None = Field(default=None, ge=1, le=500)
    atr_length: int | None = Field(default=None, ge=1, le=500)
    multiplier: float | None = Field(default=None, gt=0, le=10)

    @model_validator(mode="after")
    def _params_match_kind(self):
        required = ["length"] if self.kind == "ema" else ["ema_length", "atr_length", "multiplier"]
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.id}: missing {', '.join(missing)}")
        return self


class WatchlistUpdate(BaseModel):
    symbols: list[str]


def _validate_config(entries: list[IndicatorSetting]) -> list[dict]:
    """The indicator set is fixed: same ids, kinds and timeframes as DEFAULT_CONFIG. Returns default order."""
    by_id = {e.id: e for e in entries}
    expected = {c["id"]: c for c in DEFAULT_CONFIG}
    if set(by_id) != set(expected) or len(entries) != len(expected):
        raise ValueError(f"indicator ids must be exactly: {', '.join(expected)}")
    for id_, e in by_id.items():
        if (e.kind, e.tf) != (expected[id_]["kind"], expected[id_]["tf"]):
            raise ValueError(f"{id_}: kind/tf cannot be changed")
    return [by_id[id_].model_dump(exclude_none=True) for id_ in expected]


def load_config(conn: sqlite3.Connection) -> list[dict]:
    stored = db.get_setting(conn, INDICATORS_KEY)
    if stored is None:
        return DEFAULT_CONFIG
    try:
        return _validate_config([IndicatorSetting(**e) for e in stored])
    except (ValueError, TypeError):
        log.warning("stored indicator settings invalid; using defaults")
        return DEFAULT_CONFIG


# ---------------------------------------------------------------- data freshness

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lookup_name(ticker: str) -> tuple[str | None, str | None]:
    try:
        for q in search_quotes(ticker, max_results=5):
            if q.get("symbol") == ticker:
                return q.get("longname") or q.get("shortname"), q.get("exchDisp")
    except Exception:
        log.exception("name lookup failed for %s", ticker)
    return None, None


def ensure_data(conn: sqlite3.Connection, ticker: str, force: bool = False) -> dict:
    """Fetch `ticker` if unstored or stale (> FETCH_THROTTLE). Returns {'healed', 'stale'}.

    On a network failure with data already stored, serves what's there (stale=True).
    """
    stored = db.date_range(conn, ticker)
    sym = db.get_symbol(conn, ticker) or {}
    last = sym.get("last_fetched")
    if stored and not force and last and _now() - datetime.fromisoformat(last) < FETCH_THROTTLE:
        return {"healed": False, "stale": False}

    start = parse_lookback(DEFAULT_LOOKBACK) if stored is None else stored[0].date()
    try:
        summary = fetch_ticker(conn, ticker, start)
    except Exception as exc:
        log.exception("fetch failed for %s", ticker)
        if stored is None:
            raise HTTPException(502, f"Fetching {ticker} failed: {exc}") from exc
        return {"healed": False, "stale": True}

    if summary["range"] is None:
        raise HTTPException(404, f"No data found for {ticker}")
    name, exchange = (sym.get("name"), sym.get("exchange"))
    if not name:
        name, exchange = _lookup_name(ticker)
    db.upsert_symbol(conn, ticker, name, exchange, _now().isoformat())
    return {"healed": summary["healed"], "stale": False}


# ---------------------------------------------------------------- serialization

def _times(index: pd.DatetimeIndex, tf: str) -> list[str]:
    # Weekly bars are labelled by their W-FRI end; TradingView labels weeks by their Monday.
    if tf == "W":
        index = index - pd.Timedelta(days=4)
    return index.strftime("%Y-%m-%d").tolist()


def _series_points(series: pd.Series, tf: str) -> list[dict]:
    series = series.dropna()
    return [{"time": t, "value": round(float(v), 4)} for t, v in zip(_times(series.index, tf), series)]


def _watchlist_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = []
    for ticker in db.get_watchlist(conn):
        closes = db.last_two_closes(conn, ticker)
        sym = db.get_symbol(conn, ticker) or {}
        last = closes[0] if closes else None
        change = closes[0] - closes[1] if len(closes) == 2 else None
        rows.append({
            "symbol": ticker,
            "name": sym.get("name"),
            "last": last,
            "change": change,
            "change_pct": change / closes[1] * 100 if change is not None and closes[1] else None,
        })
    return rows


# ---------------------------------------------------------------- routes

@app.get("/api/search")
def search(q: str, conn: sqlite3.Connection = Depends(get_conn)):
    q = q.strip()
    if not q:
        return []
    try:
        quotes = search_quotes(q)
    except Exception as exc:
        raise HTTPException(502, f"Symbol search failed: {exc}") from exc

    stored = {row[0] for row in db.list_tickers(conn)}
    results = []
    for quote in quotes:
        if quote.get("quoteType") not in SEARCH_TYPES or not quote.get("symbol"):
            continue
        symbol, name = quote["symbol"], quote.get("longname") or quote.get("shortname")
        # Remember names so the chart header can show them without another lookup.
        db.upsert_symbol(conn, symbol, name, quote.get("exchDisp"))
        results.append({"symbol": symbol, "name": name, "exchange": quote.get("exchDisp"),
                        "type": quote.get("typeDisp") or quote["quoteType"], "stored": symbol in stored})
    return results[:10]


@app.get("/api/chart/{ticker}")
def chart(ticker: str, tf: Literal["D", "W"] = "D", refresh: bool = False,
          conn: sqlite3.Connection = Depends(get_conn)):
    ticker = ticker.upper()
    status = ensure_data(conn, ticker, force=refresh)
    daily = db.load_bars(conn, ticker)
    if daily.empty:
        raise HTTPException(404, f"No data found for {ticker}")

    bars = daily if tf == "D" else to_weekly(daily)
    indicators = build_indicators(daily, load_config(conn), tf)
    times = _times(bars.index, tf)
    sym = db.get_symbol(conn, ticker) or {}
    return {
        "symbol": ticker,
        "name": sym.get("name"),
        "exchange": sym.get("exchange"),
        "tf": tf,
        "bars": [
            {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": int(v)}
            for t, o, h, l, c, v in zip(times, bars["open"], bars["high"], bars["low"],
                                        bars["close"], bars["volume"])
        ],
        "indicators": {key: _series_points(s, tf) for key, s in indicators.items()},
        **status,
    }


@app.get("/api/settings/indicators")
def get_indicator_settings(conn: sqlite3.Connection = Depends(get_conn)):
    return load_config(conn)


@app.put("/api/settings/indicators")
def put_indicator_settings(entries: list[IndicatorSetting], conn: sqlite3.Connection = Depends(get_conn)):
    try:
        config = _validate_config(entries)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.put_setting(conn, INDICATORS_KEY, config)
    return config


@app.delete("/api/settings/indicators")
def reset_indicator_settings(conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (INDICATORS_KEY,))
    return DEFAULT_CONFIG


@app.get("/api/watchlist")
def get_watchlist(conn: sqlite3.Connection = Depends(get_conn)):
    return _watchlist_rows(conn)


@app.put("/api/watchlist")
def put_watchlist(body: WatchlistUpdate, conn: sqlite3.Connection = Depends(get_conn)):
    tickers = list(dict.fromkeys(s.strip().upper() for s in body.symbols if s.strip()))
    for ticker in tickers:
        if db.date_range(conn, ticker) is None:
            ensure_data(conn, ticker)  # 404/502 propagate: don't save a list containing a bad ticker
    db.set_watchlist(conn, tickers)
    return _watchlist_rows(conn)


@app.post("/api/watchlist/refresh")
def refresh_watchlist(force: bool = False, conn: sqlite3.Connection = Depends(get_conn)):
    for ticker in db.get_watchlist(conn):
        try:
            ensure_data(conn, ticker, force=force)
        except HTTPException:
            log.warning("watchlist refresh failed for %s", ticker)
    return _watchlist_rows(conn)


# Serve the built React app (production / Docker). Mounted last so /api routes win.
STATIC_DIR = Path(os.environ.get("KACHING_STATIC", Path(__file__).resolve().parent.parent / "frontend" / "dist"))
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
