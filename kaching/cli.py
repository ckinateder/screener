"""Command line entry point: fetch / list / serve."""
import argparse
import sys

from kaching import db
from kaching.analysis.checklist import run_checklist
from kaching.fetcher import fetch_ticker, parse_lookback
from kaching.market_info import get_market_info


def sector_input(conn, ticker, info):
    """#10 input; lives in the API module (it reuses the API's fetch/throttle logic)."""
    from kaching.api import sector_input as _sector_input  # lazy: keeps `fetch`/`list` free of FastAPI imports
    return _sector_input(conn, ticker, info)


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


def cmd_check(args) -> int:
    conn = db.connect()
    tickers = db.get_watchlist(conn) if args.watchlist else [t.upper() for t in args.tickers]
    if not tickers:
        print("No tickers given (and the watchlist is empty)", file=sys.stderr)
        return 1
    def mark(c):  # ✓ pass · ◐ near (graded, 50-99) · ✗ fail · – n/a
        if c["passed"] is None:
            return "–"
        if c["passed"]:
            return "✓"
        return "◐" if c["score"] is not None and c["score"] >= 50 else "✗"
    for ticker in tickers:
        stored = db.date_range(conn, ticker)
        try:  # bring data up to date first (all history if new)
            fetch_ticker(conn, ticker, stored[0].date() if stored else parse_lookback("MAX"))
        except Exception as exc:  # yfinance raises a variety of network/parse errors
            print(f"{ticker}: fetch failed ({exc}); using stored data", file=sys.stderr)
        daily = db.load_bars(conn, ticker)
        if daily.empty:
            print(f"\n{ticker}: no data")
            continue
        info = get_market_info(conn, ticker)
        _, sector = sector_input(conn, ticker, info)
        result = run_checklist(daily, info, sector=sector)
        gates = result["gates"]
        failed = f" ({', '.join(gates['failed'])})" if gates["failed"] else ""
        score = "–" if result["score"] is None else result["score"]
        print(f"\n{ticker}  score {score} · gates {gates['passed']}/{gates['applicable']}{failed}  "
              f"(as of {result['as_of']})")
        for c in result["checks"]:
            score = f"{c['score']:>3}" if c["score"] is not None else "   "
            print(f"  {mark(c)} {score} {c['label']:<32} {c['value']:<44} [{c['threshold']}]")
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
    when.add_argument("--period", default="MAX",
                      help="lookback: MAX (all available history, default) or e.g. 5Y, 6M, 2W, 30D")
    when.add_argument("--start", help="start date YYYY-MM-DD")
    p_fetch.set_defaults(func=cmd_fetch)

    p_check = sub.add_parser("check", help="run the Chart Checklist (strategy-rules.md) on tickers")
    p_check.add_argument("tickers", nargs="*")
    p_check.add_argument("--watchlist", action="store_true", help="check every watchlist ticker")
    p_check.set_defaults(func=cmd_check)

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
