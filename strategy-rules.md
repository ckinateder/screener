# Strategy Rules

## Weekly Checklist

Sunday evening routine. About 20 to 30 minutes. Produces a focused, prioritized list.

1. Open Finviz Heat Map — which sectors are green this week? Which are red?
2. Check IBD Industry Group Rankings — which groups are rising? Any new momentum building?
3. For each promising sector — pull up the sector ETF chart. Does it pass the checklist? (Chapter 3)
4. For each sector with a healthy ETF — look at two or three individual stocks within it.
5. Run the 60-second checklist on each candidate. Keep the ones that pass.
6. Update your watchlist — remove deteriorated charts, add new candidates.
7. Note earnings dates for every stock on the list.

### Chart Checklist

The 60-second chart check. Once charts are set up, evaluating a stock takes about 60 seconds. Run through this before considering any KaChing trade.

| #  | Check              | Measured as                                                                       | Pass when                                       |
|----|--------------------|-----------------------------------------------------------------------------------|-------------------------------------------------|
| 1  | Weekly trend       | last two weekly swing highs and lows, over the last 1 year                        | both rising, and price above the last swing low |
| 2  | Daily in sync      | the same test on daily bars                                                       | both timeframes up                              |
| 3  | Last 90 days       | 63-day return and trend slope                                                     | both positive                                   |
| 4  | vs 21 EMA          | % of the last 20 closes above it                                                  | ≥ 80%, and above now                            |
| 5  | vs 50 MA           | distance above the SMA 50, in ATRs                                                | ≥ 1 ATR ("room to spare")                       |
| 6  | Keltner position   | where price sits in the channel (0 = middle line, 1 = upper band), 5-day average | 0.5 – 1.1                                      |
| 7  | Volume             | up-day ÷ down-day volume over 50 days                                             | ≥ 1.0; n/a for funds                            |
| 8  | Price in range     | last close                                                                        | $25 – $300 (sweet spot for spread math)         |
| 9  | Support layers     | weekly support zones below price (W Support defaults)                             | ≥ 2 zones (the uptrend half is #1)              |
| 10 | Not a vertical run | 20-day gain, and straightness (net move ÷ total daily movement; 1 = straight line) | fails only if > 15% gain **and** straightness ≥ 0.4 |
| 11 | Average volume     | 50-day average daily volume                                                       | ≥ 1M shares; n/a for funds                      |
| 12 | Weekly expirations | option expiration dates in the next 4 weeks (Yahoo, refreshed daily)              | an expiration in each of the next 4 weeks       |
| 13 | Earnings window    | next earnings date (Yahoo, refreshed daily)                                       | more than 6 weeks (42 days) away                |
| 14 | Sector ETF         | the sector ETF's checks 1–3 (ETF suggested from Yahoo industry/sector, or your override); RS vs SPY shown | the ETF passes all three trend checks |

#### Scoring

- **Graded checks** (1–7, 9, 10, 14) score **0–100**: exactly 100 when the check passes, falling off below
  the threshold (50 about one threshold-width short, 0 two widths short). Marks: ✓ pass · ◐ near (50–99) · ✗ fail (< 50).
- **Chart score** = half the average of all graded checks + half the average of the **3 weakest**, so a few
  weak checks cost real points instead of being diluted.
- **Gates** (8 price range, 11 average volume, 12 weekly expirations, 13 earnings) are must-haves: pass/fail only,
  counted separately (e.g. "gates 3/4"). A failed gate outlines the watchlist score in red.
- The score curves are constants at the top of `kaching/analysis/checklist.py`.

### Full Qualifying Checklist

The quick qualification checklist. Before opening any chart, every box needs a check before a stock makes the list for the week. About 60 seconds. (Price range, support layers, vertical run and average volume moved to the Chart Checklist as #8–#11; weekly expirations and earnings as #12–#13; sector ETF as #14.)

| # | What to Check | Green Light |
| --- | --- | --- |
| 1 | Options chain liquidity | Bid/ask 10–20 cents or less, strong open interest |
| 2 | ATM premium justifies the trade | Friday put pays enough for the margin and risk |

