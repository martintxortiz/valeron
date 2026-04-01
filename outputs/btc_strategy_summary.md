# BTC Strategy Ranking (BTC-USD)

- Data start: 2017-01-01
- Data end: 2026-04-01
- Bars: 3378
- Fee per side: 0.1000%
- Strategies tested: 22

## Top 5

| Strategy | score | total_return_pct | cagr_pct | sharpe | sortino | calmar | max_drawdown_pct | exposure_pct | trades | win_rate_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ichimoku Cloud Trend | 79.87 | 11108.83 | 66.6 | 1.42 | 1.38 | 1.2 | -55.69 | 38.1 | 63.0 | 36.51 |
| ATR Trailing Trend | 79.22 | 12308.08 | 68.44 | 1.38 | 1.41 | 1.11 | -61.48 | 44.38 | 76.0 | 31.58 |
| Triple EMA 10/20/50 | 72.08 | 9885.03 | 64.53 | 1.32 | 1.31 | 0.95 | -68.13 | 43.43 | 51.0 | 37.25 |
| VWMA 20 Trend | 70.78 | 8837.76 | 62.57 | 1.39 | 1.39 | 1.27 | -49.1 | 37.74 | 114.0 | 32.46 |
| EMA 20/50 Trend | 69.48 | 9846.32 | 64.46 | 1.22 | 1.31 | 0.96 | -67.29 | 55.48 | 27.0 | 40.74 |

## Notes

- These are Python approximations of common TradingView/Pine strategy archetypes, not exact clones of individual public scripts.
- Signals are lagged one bar in the backtest to reduce lookahead bias.
- Ranking score is the average percentile rank across return, CAGR, Sharpe, Sortino, Calmar, drawdown, and win rate.