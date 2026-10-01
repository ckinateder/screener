"""FastAPI backend for the React app. Also serves the built frontend when present."""
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Iterator, Literal

import pandas as pd
import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from kaching import db
from kaching.analysis.checklist import run_checklist
from kaching.fetcher import fetch_ticker, parse_lookback
from kaching.indicators import DEFAULT_CONFIG, RENAMED_IDS, build_indicators, build_zones, to_weekly

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK = "MAX"
FETCH_THROTTLE = timedelta(minutes=5)
SEARCH_TYPES = {"EQUITY", "ETF", "INDEX", "MUTUALFUND"}
INDICATORS_KEY = "indicators"  # chart pane 1; pane N > 1 uses "indicators:N"

Pane = Annotated[int, Query(ge=1, le=2)]  # Literal[1, 2] rejects query strings like "2"


def _indicators_key(pane: int) -> str:
    return INDICATORS_KEY if pane == 1 else f"{INDICATORS_KEY}:{pane}"

app = FastAPI(title="Kaching")
# Full-history charts are several MB of JSON (bars + ~13 indicator series); gzip shrinks them ~6x.
# Level 5, not the default 9: ~7x faster on a 10MB chart for ~10% larger output.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


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
    kind: Literal["ema", "sma", "kc", "sr"]
    tf: Literal["D", "W"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    width: int = Field(ge=1, le=4)
    visible: bool
    length: int | None = Field(default=None, ge=1, le=500)
    ema_length: int | None = Field(default=None, ge=1, le=500)
    atr_length: int | None = Field(default=None, ge=1, le=500)
    multiplier: float | None = Field(default=None, gt=0, le=10)
    # Support zones ("sr")
    pivot: int | None = Field(default=None, ge=1, le=20)
    tolerance: float | None = Field(default=None, ge=0.1, le=10)
    lookback_years: int | None = Field(default=None, ge=1, le=30)
    max_zones: int | None = Field(default=None, ge=1, le=10)
    min_touches: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def _params_match_kind(self):
        required = {
            "ema": ["length"],
            "sma": ["length"],
            "kc": ["ema_length", "atr_length", "multiplier"],
            "sr": ["pivot", "tolerance", "lookback_years", "max_zones", "min_touches"],
        }[self.kind]
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


def _upgrade_config(stored: list[dict]) -> list[dict]:
    """Bring a saved config up to the current indicator set without losing customisations:
    replaced indicators become their successors (keeping length/colour/width/visibility), and indicators
    added since the config was saved get their defaults."""
    defaults = {e["id"]: e for e in DEFAULT_CONFIG}
    upgraded = []
    for entry in stored:
        new_id = RENAMED_IDS.get(entry.get("id"))
        if new_id:
            entry = {**defaults[new_id], **{k: entry[k] for k in ("length", "color", "width", "visible") if k in entry}}
        upgraded.append(entry)
    ids = {e.get("id") for e in upgraded}
    return upgraded + [e for e in DEFAULT_CONFIG if e["id"] not in ids]


def load_config(conn: sqlite3.Connection, pane: int = 1) -> list[dict]:
    """Indicator config for a chart pane. An unconfigured pane > 1 starts as a copy of pane 1."""
    stored = db.get_setting(conn, _indicators_key(pane))
    if stored is None:
        return DEFAULT_CONFIG if pane == 1 else load_config(conn, 1)
    stored = _upgrade_config(stored)
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
    # Tickers stored before full-history fetching (or via a shorter CLI fetch) get one backfill.
    backfill = stored is not None and not sym.get("full_history")
    fresh = last and _now() - datetime.fromisoformat(last) < FETCH_THROTTLE
    if stored and not force and not backfill and fresh:
        return {"healed": False, "stale": False}

    start = parse_lookback(DEFAULT_LOOKBACK) if stored is None or backfill else stored[0].date()
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
    if start == parse_lookback(DEFAULT_LOOKBACK):
        db.mark_full_history(conn, ticker)
    return {"healed": summary["healed"], "stale": False}


# ---------------------------------------------------------------- serialization

def _times(index: pd.DatetimeIndex, tf: str) -> list[str]:
    # Weekly bars are labelled by their W-FRI end; TradingView labels weeks by their Monday.
    if tf == "W":
        index = index - pd.Timedelta(days=4)
    return index.strftime("%Y-%m-%d").tolist()


def _day(ts: pd.Timestamp, tf: str) -> str:
    """One date, labelled the way _times labels bars (weekly -> Monday)."""
    return _times(pd.DatetimeIndex([ts]), tf)[0]


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
            "checklist": _checklist_score(conn, ticker),
        })
    return rows


def _checklist_score(conn: sqlite3.Connection, ticker: str) -> dict | None:
    """Watchlist badge: how many Chart Checklist items pass, from stored bars (no fetch)."""
    daily = db.load_bars(conn, ticker)
    if daily.empty:
        return None
    result = run_checklist(daily)
    return {k: result[k] for k in ("passed", "applicable", "all_pass")}


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
def chart(ticker: str, tf: Literal["D", "W"] = "D", refresh: bool = False, pane: Pane = 1,
          conn: sqlite3.Connection = Depends(get_conn)):
    ticker = ticker.upper()
    status = ensure_data(conn, ticker, force=refresh)
    daily = db.load_bars(conn, ticker)
    if daily.empty:
        raise HTTPException(404, f"No data found for {ticker}")

    bars = daily if tf == "D" else to_weekly(daily)
    config = load_config(conn, pane)
    indicators = build_indicators(daily, config, tf)
    zones = build_zones(daily, config, tf)
    zone_tf = {c["id"]: c["tf"] for c in config}
    times = _times(bars.index, tf)
    sym = db.get_symbol(conn, ticker) or {}
    payload = {
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
        # Label zone dates by the zone's own timeframe (weekly touches -> their week's Monday), not the
        # chart's: a weekly zone on the daily chart must start at its week, not the W-FRI label.
        "zones": {
            key: [{**z, "first": _day(z["first"], zone_tf[key]), "last": _day(z["last"], zone_tf[key])} for z in zs]
            for key, zs in zones.items()
        },
        **status,
    }
    # Already plain JSON types: skip FastAPI's per-object jsonable_encoder, which takes ~0.65s on a
    # full-history chart (~225k points) vs ~0.1s for json.dumps. allow_nan=False matches FastAPI.
    return Response(json.dumps(payload, allow_nan=False), media_type="application/json")


@app.get("/api/checklist/{ticker}")
def checklist(ticker: str, conn: sqlite3.Connection = Depends(get_conn)):
    """The Chart Checklist (strategy-rules.md) for a ticker, on fresh data."""
    ticker = ticker.upper()
    ensure_data(conn, ticker)
    daily = db.load_bars(conn, ticker)
    if daily.empty:
        raise HTTPException(404, f"No data found for {ticker}")
    return {"symbol": ticker, **run_checklist(daily)}


@app.get("/api/settings/indicators")
def get_indicator_settings(pane: Pane = 1, conn: sqlite3.Connection = Depends(get_conn)):
    return load_config(conn, pane)


@app.put("/api/settings/indicators")
def put_indicator_settings(entries: list[IndicatorSetting], pane: Pane = 1,
                           conn: sqlite3.Connection = Depends(get_conn)):
    try:
        config = _validate_config(entries)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.put_setting(conn, _indicators_key(pane), config)
    return config


@app.delete("/api/settings/indicators")
def reset_indicator_settings(pane: Pane = 1, conn: sqlite3.Connection = Depends(get_conn)):
    # Store defaults explicitly (not delete): a deleted pane-2 config would fall back to pane 1's.
    db.put_setting(conn, _indicators_key(pane), DEFAULT_CONFIG)
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
