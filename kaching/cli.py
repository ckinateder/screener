"""Command line entry point: fetch / chart / list."""
import argparse
import sys
import webbrowser
from pathlib import Path

from kaching import db
from kaching.chart import build_figure, save_chart
from kaching.fetcher import fetch_ticker, parse_lookback


def _in_docker() -> bool:
    return Path("/.dockerenv").exists()


def cmd_fetch(args) -> int:
    start = parse_lookback(args.start or args.period)
    conn = db.connect()
    for ticker in args.tickers:
        try:
            s = fetch_ticker(conn, ticker, start)
        except Exception as exc:  # yfinance raises a variety of network/parse errors
            print(f"{ticker.upper()}: fetch failed — {exc}", file=sys.stderr)
            continue
        if s["range"] is None:
            print(f"{s['ticker']}: no data returned (bad ticker?)")
            continue
        lo, hi = s["range"]
        note = " (re-adjusted: full history refetched)" if s["healed"] else ""
        print(f"{s['ticker']}: {s['new_rows']:+d} rows, stored {lo:%Y-%m-%d} → {hi:%Y-%m-%d}{note}")
    return 0


def cmd_chart(args) -> int:
    conn = db.connect()
    ticker = args.ticker.upper()
    daily = db.load_bars(conn, ticker)
    if daily.empty:
        print(f"{ticker}: no data in DB — run `fetch {ticker}` first", file=sys.stderr)
        return 1
    view_start = parse_lookback(args.period) if args.period else None
    path = save_chart(build_figure(ticker, daily, view_start), ticker)
    print(f"{ticker}: chart written to {path}")
    if not args.no_open and not _in_docker():
        webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_list(_args) -> int:
    rows = db.list_tickers(db.connect())
    if not rows:
        print("DB is empty")
    for ticker, lo, hi, count in rows:
        print(f"{ticker:<8} {lo} → {hi}  ({count} bars)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kaching", description="Kaching weekly options stock selector")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="download daily bars into the DB (incremental)")
    p_fetch.add_argument("tickers", nargs="+")
    when = p_fetch.add_mutually_exclusive_group()
    when.add_argument("--period", default="5Y", help="lookback like 5Y, 6M, 2W, 30D (default 5Y)")
    when.add_argument("--start", help="start date YYYY-MM-DD")
    p_fetch.set_defaults(func=cmd_fetch)

    p_chart = sub.add_parser("chart", help="render interactive HTML chart from the DB")
    p_chart.add_argument("ticker")
    p_chart.add_argument("--period", help="initial visible range, e.g. 1Y or YYYY-MM-DD (default: all)")
    p_chart.add_argument("--no-open", action="store_true", help="don't open the chart in a browser")
    p_chart.set_defaults(func=cmd_chart)

    p_list = sub.add_parser("list", help="list stored tickers and date ranges")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
