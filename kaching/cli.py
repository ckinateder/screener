"""Command line entry point: fetch / list / serve."""
import argparse
import sys

from kaching import db
from kaching.fetcher import fetch_ticker, parse_lookback


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


def cmd_serve(args) -> int:
    import uvicorn  # imported lazily so fetch/list don't pay for it

    uvicorn.run("kaching.api:app", host=args.host, port=args.port, reload=args.reload)
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

    p_list = sub.add_parser("list", help="list stored tickers and date ranges")
    p_list.set_defaults(func=cmd_list)

    p_serve = sub.add_parser("serve", help="run the web app / API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
