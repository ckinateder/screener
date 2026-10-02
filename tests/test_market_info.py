from datetime import datetime, timedelta, timezone

import pytest

from kaching import db, market_info

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "mi.db")


@pytest.fixture
def fetches(monkeypatch):
    """Fake Yahoo: records calls, returns a weekly-options stock."""
    calls = []

    def fake(ticker):
        calls.append(ticker)
        return {"expirations": ["2026-10-02", "2026-10-09"], "earnings": "2026-11-17",
                "sector": "Technology", "industry": "Semiconductors", "quote_type": "EQUITY"}

    monkeypatch.setattr(market_info, "fetch_market_info", fake)
    return calls


def test_fetches_and_caches_for_a_day(conn, fetches):
    first = market_info.get_market_info(conn, "NVDA", now=NOW)
    assert first["earnings"] == "2026-11-17" and first["expirations"] == ["2026-10-02", "2026-10-09"]
    market_info.get_market_info(conn, "NVDA", now=NOW + timedelta(hours=23))
    assert fetches == ["NVDA"]  # second call served from cache
    market_info.get_market_info(conn, "NVDA", now=NOW + timedelta(hours=25))
    assert fetches == ["NVDA", "NVDA"]  # stale -> refetched


def test_force_refetches(conn, fetches):
    market_info.get_market_info(conn, "NVDA", now=NOW)
    market_info.get_market_info(conn, "NVDA", force=True, now=NOW)
    assert len(fetches) == 2


def test_fetch_error_serves_stale_cache(conn, fetches, monkeypatch):
    market_info.get_market_info(conn, "NVDA", now=NOW)

    def boom(ticker):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(market_info, "fetch_market_info", boom)
    stale = market_info.get_market_info(conn, "NVDA", now=NOW + timedelta(days=3))
    assert stale["earnings"] == "2026-11-17"


def test_fetch_error_without_cache_is_none(conn, monkeypatch):
    def boom(ticker):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(market_info, "fetch_market_info", boom)
    assert market_info.get_market_info(conn, "NVDA", now=NOW) is None


def test_fund_without_options_or_earnings(conn, monkeypatch):
    monkeypatch.setattr(market_info, "fetch_market_info", lambda t: {
        "expirations": [], "earnings": None, "sector": None, "industry": None, "quote_type": "MUTUALFUND"})
    result = market_info.get_market_info(conn, "FCNTX", now=NOW)
    assert result["expirations"] == [] and result["earnings"] is None


def test_classification_is_cached_with_the_rest(conn, fetches):
    market_info.get_market_info(conn, "NVDA", now=NOW)
    cached = market_info.get_market_info(conn, "NVDA", now=NOW + timedelta(hours=1))
    assert (cached["sector"], cached["industry"], cached["quote_type"]) == ("Technology", "Semiconductors", "EQUITY")
    assert fetches == ["NVDA"]


def test_migration_adds_new_columns_to_existing_tables(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE market_info (ticker TEXT PRIMARY KEY, expirations TEXT NOT NULL, "
                "earnings TEXT, fetched_at TEXT NOT NULL)")
    old.execute("INSERT INTO market_info VALUES ('NVDA', '[]', NULL, '2026-10-01T00:00:00+00:00')")
    old.execute("CREATE TABLE symbols (ticker TEXT PRIMARY KEY, name TEXT, exchange TEXT, last_fetched TEXT)")
    old.commit()
    old.close()
    conn = db.connect(path)
    assert db.get_market_info(conn, "NVDA")["sector"] is None
    db.set_sector_etf(conn, "IREN", "WGMI")
    assert db.get_sector_etf(conn, "IREN") == "WGMI"
    db.set_sector_etf(conn, "IREN", None)
    assert db.get_sector_etf(conn, "IREN") is None


def test_rows_cached_before_classification_existed_are_refetched(conn, fetches):
    # Cached earlier today by an older version: no sector/industry/quote_type columns filled.
    db.put_market_info(conn, "NVDA", {"expirations": [], "earnings": None, "fetched_at": NOW.isoformat()})
    refreshed = market_info.get_market_info(conn, "NVDA", now=NOW + timedelta(hours=1))
    assert fetches == ["NVDA"] and refreshed["industry"] == "Semiconductors"
