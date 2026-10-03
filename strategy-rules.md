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

Each scored check gets **0–100**: exactly **100 when it passes**, falling in a straight line to **0** at the
value in the last column (50 halfway). Marks: ✓ pass (100) · ◐ near (50–99) · ✗ fail (below 50).
The **chart score** is the average of checks 1–10. Gates (11–14) are must-haves: pass/fail only.

**Scored checks**

| #  | Check              | Measured as                                                                          | 100 = pass                                      | 50                                   | 0                                    |
|----|--------------------|--------------------------------------------------------------------------------------|-------------------------------------------------|--------------------------------------|--------------------------------------|
| 1  | Weekly trend       | last two weekly swing highs and lows, over the last 1 year                           | higher high **and** higher low, price above the last swing low | each half (high, low): 2.5% lower    | 5% lower; below the last swing low caps at 40 |
| 2  | Daily in sync      | the same test on daily bars (last ~6 months)                                         | weekly **and** daily trend up                   | average of the weekly and daily trend scores |                                      |
| 3  | Last 90 days       | 63-day return and trend slope (half the score each)                                  | both positive                                   | return −5% · slope −1.5%/mo          | return −10% · slope −3%/mo           |
| 4  | vs 21 EMA          | % of the last 20 closes above it, and today's close                                  | ≥ 80%, and above now                            | 60%                                  | 40%; below the EMA now caps at 49    |
| 5  | vs 50 MA           | distance above the 50-day SMA, in ATRs (14-day)                                      | ≥ 1 ATR above ("room to spare")                 | at the MA (0 ATR)                    | 1 ATR below                          |
| 6  | Keltner position   | where price sits in the channel (0 = middle line, 1 = upper band), 5-day average    | 0.5 – 1.1                                       | 0 (middle line) · 1.4 above the band | −0.5 · 1.7 above the band            |
| 7  | Volume             | up-day ÷ down-day volume over 50 days                                                | ≥ 1.0                                           | 0.8                                  | 0.6; n/a for funds                   |
| 8  | Support layers     | weekly support zones below price (W Support defaults, last 3 years)                  | ≥ 2 zones                                       | 1 zone                               | no zones                             |
| 9  | Not a vertical run | 20-day gain, and straightness (net move ÷ total daily movement; 1 = straight line)   | not (> 15% gain **and** straightness ≥ 0.4)     | —                                    | a vertical run scores 40 at a 15% gain, falling to 0 at 30% |
| 10 | Sector ETF         | the sector ETF's checks 1–3 (ETF suggested from Yahoo industry/sector, or your override); RS vs SPY shown | the ETF passes all three trend checks | average of the ETF's own scores for 1–3 |                                      |

**Gates (must-haves, pass/fail)**

| #  | Check              | Measured as                                                          | Pass when                               |
|----|--------------------|----------------------------------------------------------------------|-----------------------------------------|
| 11 | Price in range     | last close                                                           | $25 – $300 (sweet spot for spread math) |
| 12 | Average volume     | 50-day average daily volume                                          | ≥ 1M shares; n/a for funds              |
| 13 | Weekly expirations | option expiration dates in the next 4 weeks (Yahoo, refreshed daily) | an expiration in each of the next 4 weeks |
| 14 | Earnings window    | next earnings date (Yahoo, refreshed daily)                          | more than 6 weeks (42 days) away        |

A failed gate outlines the watchlist score in red. All thresholds and score curves are constants at the top
of `kaching/analysis/checklist.py`.

### Options Checklist (not yet implemented)

The quick qualification checklist. Before opening any chart, every box needs a check before a stock makes the list for the week. About 60 seconds. (Support layers, vertical run and sector ETF moved to the Chart Checklist as #8–#10; price range, average volume, weekly expirations and earnings as gates #11–#14.)

| # | What to Check | Green Light |
| --- | --- | --- |
| 1 | Options chain liquidity | Bid/ask 10–20 cents or less, strong open interest |
| 2 | ATM premium justifies the trade | Friday put pays enough for the margin and risk |

