import pandas as pd
import pytest
from fastapi.testclient import TestClient

import sqlite3
from datetime import date

from kaching import api, db, fetcher, market_info
from kaching.indicators import DEFAULT_CONFIG
from tests.test_fetcher import FakeMarket

QUOTES = [
    {"symbol": "NVDA", "longname": "NVIDIA Corporation", "exchDisp": "NASDAQ", "quoteType": "EQUITY", "typeDisp": "Equity"},
    {"symbol": "NVDA=F", "shortname": "NVIDIA future", "exchDisp": "CME", "quoteType": "FUTURE", "typeDisp": "Futures"},
    {"symbol": "NVDX", "shortname": "2X Long NVIDIA", "exchDisp": "BATS", "quoteType": "ETF", "typeDisp": "ETF"},
    {"symbol": "FCNTX", "longname": "Fidelity Contrafund", "exchDisp": "Nasdaq", "quoteType": "MUTUALFUND",
     "typeDisp": "Mutual Fund"},
]


def kc(config):
    """The daily Keltner entry of an indicator config."""
    return next(e for e in config if e["id"] == "d_kc")


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
    monkeypatch.setattr(market_info, "fetch_market_info",
                        lambda t: {"expirations": ["2099-01-02"], "earnings": "2099-03-01"})
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
    assert [r["symbol"] for r in results] == ["NVDA", "NVDX", "FCNTX"]  # futures excluded, funds kept
    assert results[2]["type"] == "Mutual Fund"
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


def test_checklist_endpoint(client):
    body = client.get("/api/checklist/aapl").json()
    assert body["symbol"] == "AAPL" and len(body["checks"]) == 13
    assert body["applicable"] <= 13 and body["as_of"]
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["earnings"]["value"].startswith("Mar 1")  # market info wired through (fake Yahoo)
    assert client.get("/api/checklist/BAD").status_code == 404


def test_watchlist_rows_include_checklist_score(client):
    rows = client.put("/api/watchlist", json={"symbols": ["AAPL"]}).json()
    score = rows[0]["checklist"]
    assert set(score) == {"passed", "applicable", "all_pass"}
    assert 0 <= score["passed"] <= score["applicable"] <= 13


def test_strategy_rules_served_live(client, tmp_path, monkeypatch):
    rules = tmp_path / "rules.md"
    rules.write_text("# Strategy Rules\n\n| # | Check |\n|---|---|\n| 1 | Weekly trend |\n", encoding="utf-8")
    monkeypatch.setenv("KACHING_RULES", str(rules))
    res = client.get("/api/strategy-rules")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/markdown")
    assert res.text.startswith("# Strategy Rules")
    rules.write_text(res.text + "| 2 | Daily in sync |\n", encoding="utf-8")  # edited -> next request sees it
    assert "Daily in sync" in client.get("/api/strategy-rules").text


def test_strategy_rules_missing_is_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KACHING_RULES", str(tmp_path / "nope.md"))
    assert client.get("/api/strategy-rules").status_code == 404


def test_strategy_rules_default_path_is_repo_file(client, monkeypatch):
    monkeypatch.delenv("KACHING_RULES", raising=False)
    assert "Chart Checklist" in client.get("/api/strategy-rules").text


def test_chart_unknown_ticker_404(client):
    assert client.get("/api/chart/BAD").status_code == 404


# ------------------------------------------------------------------ settings

def test_settings_default_roundtrip_and_reset(client):
    assert client.get("/api/settings/indicators").json() == DEFAULT_CONFIG
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    kc(cfg)["multiplier"] = 1.5
    assert client.put("/api/settings/indicators", json=cfg).status_code == 200
    assert kc(client.get("/api/settings/indicators").json())["multiplier"] == 1.5
    assert client.delete("/api/settings/indicators").json() == DEFAULT_CONFIG
    assert client.get("/api/settings/indicators").json() == DEFAULT_CONFIG


def test_settings_change_affects_chart(client):
    before = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    kc(cfg)["multiplier"] = 1.0
    client.put("/api/settings/indicators", json=cfg)
    after = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    assert after < before


def test_panes_have_independent_settings(client):
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    kc(cfg)["multiplier"] = 1.0
    client.put("/api/settings/indicators", json=cfg)  # pane 1
    # An unconfigured pane 2 starts as a copy of pane 1...
    assert kc(client.get("/api/settings/indicators", params={"pane": 2}).json())["multiplier"] == 1.0
    # ...then diverges once saved.
    cfg2 = [dict(e) for e in DEFAULT_CONFIG]
    kc(cfg2)["multiplier"] = 3.0
    client.put("/api/settings/indicators", params={"pane": 2}, json=cfg2)
    assert kc(client.get("/api/settings/indicators").json())["multiplier"] == 1.0
    assert kc(client.get("/api/settings/indicators", params={"pane": 2}).json())["multiplier"] == 3.0

    upper1 = client.get("/api/chart/AAPL").json()["indicators"]["d_kc:upper"][-1]["value"]
    upper2 = client.get("/api/chart/AAPL", params={"pane": 2}).json()["indicators"]["d_kc:upper"][-1]["value"]
    assert upper2 > upper1

    # Resetting pane 2 gives defaults, not pane 1's config; pane 1 is untouched.
    client.delete("/api/settings/indicators", params={"pane": 2})
    assert client.get("/api/settings/indicators", params={"pane": 2}).json() == DEFAULT_CONFIG
    assert kc(client.get("/api/settings/indicators").json())["multiplier"] == 1.0
    assert client.get("/api/settings/indicators", params={"pane": 3}).status_code == 422


def test_chart_includes_support_zones(client, market):
    # Oscillating prices on a rising trend, so there are swing lows below the latest close.
    import numpy as np
    n = len(market.bars)
    close = 100 + np.arange(n) * 0.2 + 8 * np.sin(np.arange(n) / 6)
    market.bars["close"] = close
    market.bars["open"], market.bars["high"], market.bars["low"] = close, close + 1, close - 1

    daily = client.get("/api/chart/AAPL", params={"tf": "D"}).json()
    weekly = client.get("/api/chart/AAPL", params={"tf": "W"}).json()
    assert set(daily["zones"]) == {"d_sr", "w_sr"}
    assert set(weekly["zones"]) == {"w_sr"}  # daily support isn't shown on weekly candles
    zones = daily["zones"]["w_sr"]
    assert 0 < len(zones) <= 3
    last_close = daily["bars"][-1]["close"]
    for z in zones:
        assert set(z) == {"low", "high", "touches", "first", "last"}
        assert z["low"] <= z["high"] and (z["low"] + z["high"]) / 2 < last_close
        assert pd.Timestamp(z["first"]).day_name() == "Monday"  # weekly zones use Monday labels


def test_old_saved_config_keeps_customisations_when_indicators_are_added(client):
    # A config saved before support zones existed: no sr entries, customised Keltner.
    old = [dict(e) for e in DEFAULT_CONFIG if e["kind"] != "sr"]
    kc(old)["multiplier"] = 1.1
    conn = db.connect()
    db.put_setting(conn, "indicators", old)
    cfg = client.get("/api/settings/indicators").json()
    assert kc(cfg)["multiplier"] == 1.1
    assert {e["id"] for e in cfg} == {e["id"] for e in DEFAULT_CONFIG}


def test_saved_ema_50_100_migrate_to_sma_keeping_style(client):
    # Config saved when the 50/100 lines were EMAs, with a customised (hidden, recoloured) EMA 50.
    old = [dict(e) for e in DEFAULT_CONFIG if e["kind"] != "sma"]
    for tf in ("d", "w"):
        for n in (50, 100):
            old.append({"id": f"{tf}_ema_{n}", "kind": "ema", "tf": tf.upper(), "length": n,
                        "color": "#123456", "width": 3, "visible": False})
    db.put_setting(db.connect(), "indicators", old)

    cfg = {e["id"]: e for e in client.get("/api/settings/indicators").json()}
    assert "d_ema_50" not in cfg and "w_ema_100" not in cfg
    migrated = cfg["d_sma_50"]
    assert (migrated["kind"], migrated["length"]) == ("sma", 50)
    assert (migrated["color"], migrated["width"], migrated["visible"]) == ("#123456", 3, False)


def test_chart_sma_series(client):
    ind = client.get("/api/chart/AAPL").json()["indicators"]
    assert {"d_sma_50", "d_sma_100", "w_sma_50", "w_sma_100"} <= set(ind)
    assert not {"d_ema_50", "d_ema_100"} & set(ind)


def test_support_settings_validate_params(client):
    cfg = [dict(e) for e in DEFAULT_CONFIG]
    sr = next(e for e in cfg if e["id"] == "w_sr")
    sr["tolerance"] = 0.5
    assert client.put("/api/settings/indicators", json=cfg).status_code == 200
    sr["max_zones"] = 0
    assert client.put("/api/settings/indicators", json=cfg).status_code == 422
    sr["max_zones"] = 3
    del sr["pivot"]
    assert client.put("/api/settings/indicators", json=cfg).status_code == 422


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
