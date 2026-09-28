import pandas as pd
import pytest
from fastapi.testclient import TestClient

import sqlite3
from datetime import date

from kaching import api, db, fetcher
from kaching.indicators import DEFAULT_CONFIG
from tests.test_fetcher import FakeMarket

QUOTES = [
    {"symbol": "NVDA", "longname": "NVIDIA Corporation", "exchDisp": "NASDAQ", "quoteType": "EQUITY", "typeDisp": "Equity"},
    {"symbol": "NVDA=F", "shortname": "NVIDIA future", "exchDisp": "CME", "quoteType": "FUTURE", "typeDisp": "Futures"},
    {"symbol": "NVDX", "shortname": "2X Long NVIDIA", "exchDisp": "BATS", "quoteType": "ETF", "typeDisp": "ETF"},
]


class Market(FakeMarket):
    """FakeMarket that knows only real-looking tickers; 'BAD' returns nothing."""

    def __call__(self, ticker, start, end):
        bars = super().__call__(ticker, start, end)
        return bars.iloc[0:0] if ticker == "BAD" else bars


@pytest.fixture
def market(monkeypatch):
    m = Market()
    monkeypatch.setattr(fetcher, "download", m)
    return m


@pytest.fixture
def client(tmp_path, monkeypatch, market):
    monkeypatch.setenv("KACHING_DB", str(tmp_path / "api.db"))
    monkeypatch.setattr(api, "search_quotes", lambda q, max_results=15: QUOTES)
    return TestClient(api.app)


def test_connection_usable_across_threads(tmp_path, monkeypatch):
    # Regression: FastAPI runs sync dependencies and endpoints on different threadpool threads.
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv("KACHING_DB", str(tmp_path / "t.db"))
    gen = api.get_conn()  # keep a reference: GC of the generator would close the connection
    conn = next(gen)
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(lambda: conn.execute("SELECT 1").fetchone()).result() == (1,)


# ------------------------------------------------------------------ search

def test_search_filters_types_and_flags_stored(client):
    client.get("/api/chart/NVDA")
    results = client.get("/api/search", params={"q": "nvid"}).json()
    assert [r["symbol"] for r in results] == ["NVDA", "NVDX"]
    assert results[0] == {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ",
                          "type": "Equity", "stored": True}
    assert results[1]["stored"] is False


def test_search_empty_query(client):
    assert client.get("/api/search", params={"q": "  "}).json() == []


def test_search_upstream_failure_is_502(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(api, "search_quotes", boom)
    assert client.get("/api/search", params={"q": "x"}).status_code == 502


# ------------------------------------------------------------------ chart

def test_chart_autofetches_and_names_symbol(client, market):
    body = client.get("/api/chart/nvda").json()
    assert body["symbol"] == "NVDA" and body["name"] == "NVIDIA Corporation"
    assert len(body["bars"]) == len(market.bars)
    assert set(body["bars"][0]) == {"time", "open", "high", "low", "close", "volume"}


def test_chart_is_throttled_unless_refresh(client, market):
    client.get("/api/chart/AAPL")
    market.calls.clear()
    client.get("/api/chart/AAPL")
    assert market.calls == []
    client.get("/api/chart/AAPL", params={"refresh": 1})
    assert market.calls  # forced incremental fetch


def test_chart_daily_vs_weekly_indicators(client):
    daily = client.get("/api/chart/AAPL", params={"tf": "D"}).json()
    weekly = client.get("/api/chart/AAPL", params={"tf": "W"}).json()
    assert {"d_ema_9", "w_ema_21", "d_kc:upper", "w_kc:lower"} <= set(daily["indicators"])
    assert all(k.startswith("w_") for k in weekly["indicators"])
    assert len(weekly["bars"]) < len(daily["bars"])
    # weekly bars are labelled by Monday, like TradingView
    assert {pd.Timestamp(b["time"]).day_name() for b in weekly["bars"]} == {"Monday"}


def test_stored_short_history_is_backfilled_once(client, market):
    # A ticker stored with only recent history (e.g. before MAX, or via `fetch --period 5Y`).
    conn = db.connect()
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1))
    assert db.date_range(conn, "AAPL")[0] == pd.Timestamp("2024-01-01")

    client.get("/api/chart/AAPL")
    assert db.date_range(conn, "AAPL")[0] == market.bars.index[0]  # all available history
    assert db.get_symbol(conn, "AAPL")["full_history"] == 1

    market.calls.clear()
    client.get("/api/chart/AAPL", params={"refresh": 1})
    assert all(start > pd.Timestamp("2000-01-01") for start, _ in market.calls)  # no repeat backfill


def test_new_ticker_fetches_from_earliest(client, market):
    client.get("/api/chart/NVDA")
    assert market.calls[0][0] == pd.Timestamp(fetcher.EARLIEST_START)


def test_migrates_old_symbols_table(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE symbols (ticker TEXT PRIMARY KEY, name TEXT, exchange TEXT, last_fetched TEXT)")
    old.execute("INSERT INTO symbols VALUES ('AAPL', 'Apple', 'NASDAQ', NULL)")
    old.commit()
    old.close()
    assert db.get_symbol(db.connect(path), "AAPL")["full_history"] == 0


def test_large_responses_are_gzipped(client):
    res = client.get("/api/chart/AAPL", headers={"Accept-Encoding": "gzip"})
    assert res.headers["content-encoding"] == "gzip"


def test_chart_unknown_ticker_404(client):
    assert client.get("/api/chart/BAD").status_code == 404


# ------------------------------------------------------------------ settings

def test_settings_default_roundtrip_and_reset(client):
    assert client.get("/api/settings/indicators").json() == DEFAULT_CONFIG
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    cfg[-2]["multiplier"] = 1.5
    assert client.put("/api/settings/indicators", json=cfg).status_code == 200
    assert client.get("/api/settings/indicators").json()[-2]["multiplier"] == 1.5
    assert client.delete("/api/settings/indicators").json() == DEFAULT_CONFIG
    assert client.get("/api/settings/indicators").json() == DEFAULT_CONFIG


def test_settings_change_affects_chart(client):
    before = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    cfg[-2]["multiplier"] = 1.0
    client.put("/api/settings/indicators", json=cfg)
    after = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    assert after < before


def test_panes_have_independent_settings(client):
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    cfg[-2]["multiplier"] = 1.0
    client.put("/api/settings/indicators", json=cfg)  # pane 1
    # An unconfigured pane 2 starts as a copy of pane 1...
    assert client.get("/api/settings/indicators", params={"pane": 2}).json()[-2]["multiplier"] == 1.0
    # ...then diverges once saved.
    cfg2 = [dict(e) for e in DEFAULT_CONFIG]
    cfg2[-2]["multiplier"] = 3.0
    client.put("/api/settings/indicators", params={"pane": 2}, json=cfg2)
    assert client.get("/api/settings/indicators").json()[-2]["multiplier"] == 1.0
    assert client.get("/api/settings/indicators", params={"pane": 2}).json()[-2]["multiplier"] == 3.0

    upper1 = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    upper2 = client.get("/api/chart/AAPL", params={"pane": 2}).json()["indicators"]["d_kc:upper"][-1]["value"]
    assert upper2 > upper1

    # Resetting pane 2 gives defaults, not pane 1's config; pane 1 is untouched.
    client.delete("/api/settings/indicators", params={"pane": 2})
    assert client.get("/api/settings/indicators", params={"pane": 2}).json() == DEFAULT_CONFIG
    assert client.get("/api/settings/indicators").json()[-2]["multiplier"] == 1.0
    assert client.get("/api/settings/indicators", params={"pane": 3}).status_code == 422


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop(),                                  # missing indicator
    lambda c: c[0].update(color="red"),                 # bad colour
    lambda c: c[0].update(kind="kc"),                   # kind change (and missing KC params)
    lambda c: c[0].update(tf="W"),                      # tf change
    lambda c: c[0].update(length=0),                    # out of range
    lambda c: c.append(dict(c[0], id="extra")),         # unknown id
])
def test_settings_validation(client, mutate):
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    mutate(cfg)
    assert client.put("/api/settings/indicators", json=cfg).status_code == 422


# ------------------------------------------------------------------ watchlist

def test_watchlist_order_and_change(client, market):
    rows = client.put("/api/watchlist", json={"symbols": ["msft", "AAPL", "MSFT"]}).json()
    assert [r["symbol"] for r in rows] == ["MSFT", "AAPL"]
    last, prev = market.bars["close"].iloc[-1], market.bars["close"].iloc[-2]
    assert rows[0]["last"] == last
    assert rows[0]["change"] == pytest.approx(last - prev)
    assert rows[0]["change_pct"] == pytest.approx((last - prev) / prev * 100)
    rows = client.put("/api/watchlist", json={"symbols": ["AAPL", "MSFT"]}).json()
    assert [r["symbol"] for r in client.get("/api/watchlist").json()] == ["AAPL", "MSFT"]


def test_watchlist_rejects_bad_ticker_without_saving(client):
    client.put("/api/watchlist", json={"symbols": ["AAPL"]})
    assert client.put("/api/watchlist", json={"symbols": ["AAPL", "BAD"]}).status_code == 404
    assert [r["symbol"] for r in client.get("/api/watchlist").json()] == ["AAPL"]


def test_watchlist_refresh_respects_throttle(client, market):
    client.put("/api/watchlist", json={"symbols": ["AAPL", "MSFT"]})
    market.calls.clear()
    client.post("/api/watchlist/refresh")
    assert market.calls == []
    client.post("/api/watchlist/refresh", params={"force": True})
    assert len(market.calls) == 2
