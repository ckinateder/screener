from datetime import date

import pandas as pd
import pytest

from kaching import db, fetcher

TODAY = date(2024, 3, 29)


class FakeMarket:
    """Stands in for yfinance: serves [start, end) slices of a fixed series and records calls."""

    def __init__(self, start="2023-01-02", end="2024-03-29", scale=1.0):
        idx = pd.bdate_range(start, end)
        close = pd.Series(range(1, len(idx) + 1), index=idx, dtype=float) * scale
        self.bars = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                                  "close": close, "volume": 1000})
        self.calls = []

    def __call__(self, ticker, start, end):
        self.calls.append((pd.Timestamp(start), pd.Timestamp(end)))
        b = self.bars
        return b[(b.index >= pd.Timestamp(start)) & (b.index < pd.Timestamp(end))].copy()


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "test.db")


@pytest.fixture
def market(monkeypatch):
    m = FakeMarket()
    monkeypatch.setattr(fetcher, "download", m)
    return m


@pytest.mark.parametrize("value,expected", [
    ("5Y", date(2019, 3, 29)),
    ("6m", date(2023, 9, 29)),
    ("2W", date(2024, 3, 15)),
    ("30D", date(2024, 2, 28)),
    ("2020-01-15", date(2020, 1, 15)),
])
def test_parse_lookback(value, expected):
    assert fetcher.parse_lookback(value, today=TODAY) == expected


@pytest.mark.parametrize("bad", ["5X", "Y5", "2024/01/01", ""])
def test_parse_lookback_rejects_garbage(bad):
    with pytest.raises(ValueError):
        fetcher.parse_lookback(bad, today=TODAY)


def test_first_fetch_stores_full_range(conn, market):
    s = fetcher.fetch_ticker(conn, "aapl", date(2024, 1, 1), today=TODAY)
    assert s["ticker"] == "AAPL"
    assert s["range"] == (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-29"))
    assert s["new_rows"] == len(pd.bdate_range("2024-01-01", "2024-03-29"))


def test_refetch_adds_only_new_dates(conn, market):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=date(2024, 3, 15))
    market.calls.clear()
    s = fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    assert s["new_rows"] == 10  # Mar 18..29
    assert not s["healed"]
    # only one download, starting at the anchor (second-to-last stored bar), not from Jan 1
    assert market.calls == [(pd.Timestamp("2024-03-14"), pd.Timestamp("2024-03-30"))]


def test_refetch_same_day_is_noop(conn, market):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    s = fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    assert s["new_rows"] == 0 and not s["healed"]


def test_partial_last_bar_is_overwritten_without_heal(conn, market):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    market.bars.loc["2024-03-29", "close"] += 5  # intraday bar moved
    s = fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    assert not s["healed"]
    assert db.load_bars(conn, "AAPL")["close"].iloc[-1] == market.bars["close"].iloc[-1]


def test_backfill_older_dates(conn, market):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    market.calls.clear()
    s = fetcher.fetch_ticker(conn, "AAPL", date(2023, 6, 1), today=TODAY)
    assert s["range"][0] == pd.Timestamp("2023-06-01")
    assert s["new_rows"] == len(pd.bdate_range("2023-06-01", "2023-12-31"))
    assert (pd.Timestamp("2023-06-01"), pd.Timestamp("2024-01-01")) in market.calls


def test_split_triggers_full_refetch(conn, market, monkeypatch):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=date(2024, 3, 15))
    adjusted = FakeMarket(scale=0.5)  # history re-adjusted, e.g. 2:1 split
    monkeypatch.setattr(fetcher, "download", adjusted)
    s = fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    assert s["healed"]
    stored = db.load_bars(conn, "AAPL")
    expected = adjusted.bars.loc["2024-01-01":, "close"]
    assert stored["close"].tolist() == expected.tolist()


def test_tickers_are_isolated(conn, market):
    fetcher.fetch_ticker(conn, "AAPL", date(2024, 1, 1), today=TODAY)
    fetcher.fetch_ticker(conn, "MSFT", date(2024, 3, 1), today=TODAY)
    assert [r[0] for r in db.list_tickers(conn)] == ["AAPL", "MSFT"]
    assert db.date_range(conn, "MSFT")[0] == pd.Timestamp("2024-03-01")
