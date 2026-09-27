# Kaching v3

A stock selection tool for the Kaching weekly options strategy. It fetches daily bars from Yahoo Finance into a local SQLite database, then renders an interactive chart with daily and weekly EMAs and Keltner Channels.

## Indicators

| Indicator | Daily | Weekly |
|---|---|---|
| EMA 9 | ✓ | |
| EMA 21 / 50 / 100 | ✓ | ✓ |
| Keltner Channel: EMA(20) mid, ±2.0 × ATR(10) | ✓ | ✓ |

- ATR uses Wilder (RMA) smoothing, the same as TradingView's `ta.atr`.
- Weekly bars are resampled from stored daily bars into weeks ending Friday. The current week uses its in-progress values.
- Indicators are computed over the full stored history, so fetch more history than you want to view. EMA 100 on a weekly chart needs about 2 years to warm up.
- Prices are **adjusted** for splits and dividends.

## Quick start (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m kaching fetch AAPL --period 5Y       # or --start 2020-01-01
python -m kaching fetch AAPL MSFT NVDA         # several at once (default lookback: 5Y)
python -m kaching chart AAPL --period 1Y       # writes charts/AAPL.html and opens it
python -m kaching list                         # stored tickers and date ranges
```

Lookback formats are `5Y`, `6M`, `2W`, `30D` (counted back from today) or a `YYYY-MM-DD` start date.

### Chart

- Click a legend item to show or hide it. Each Keltner Channel (upper, mid and lower) toggles as one item.
- Daily and weekly EMAs of the same length share a colour. Weekly lines are dashed step lines. Weekly EMAs are hidden until you click them.
- Use the range buttons (3M / 6M / 1Y / 5Y / All) or drag to zoom. `chart --period` only sets the initial view.
- The HTML loads plotly.js from a CDN, so viewing it needs internet access.

## Docker

```bash
docker build -t kaching .
docker run --rm -v "$PWD/data:/data" kaching fetch AAPL --period 5Y
docker run --rm -v "$PWD/data:/data" kaching chart AAPL
open data/charts/AAPL.html
```

The container can't open a browser, so the chart is written to `./data/charts/` on the host.

## Storage and incremental fetching

All tickers share one SQLite DB in the table `bars(ticker, date, open, high, low, close, volume)`.

When you fetch a ticker that's already stored:

1. **New dates.** Only bars after the latest stored date are downloaded. The latest bar is always rewritten, because a fetch during market hours stores a partial day.
2. **Backfill.** If the requested start is earlier than the stored history, only the missing older range is downloaded.
3. **Auto-heal.** Yahoo re-adjusts history after splits and dividends. Each fetch re-checks one stored bar, and if its close has changed, that ticker's history is deleted and refetched. The output says `re-adjusted` when this happens.

## Configuration

| Env var | Default | Docker |
|---|---|---|
| `KACHING_DB` | `data/kaching.db` | `/data/kaching.db` |
| `KACHING_CHARTS` | `charts` | `/data/charts` |

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

Tests don't use the network: yfinance is replaced with a fake in `tests/test_fetcher.py`.

## Layout

```
kaching/
  cli.py         argparse subcommands: fetch / chart / list
  fetcher.py     yfinance download, lookback parsing, incremental + auto-heal logic
  db.py          SQLite schema and queries
  indicators.py  EMA, ATR, Keltner, weekly resampling
  chart.py       Plotly figure
```
