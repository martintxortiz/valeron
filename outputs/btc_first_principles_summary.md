# BTC First-Principles Strategy

## Idea

- Trend persistence: only participate when short trend is above long trend and price is above the long trend.
- Convexity: require an n-day breakout so we are paying for strength, not guessing bottoms.
- Volatility clustering: scale exposure inversely with realized volatility instead of using fixed size.
- Fat-tail defense: exit on either a shorter breakout failure, a volatility-adjusted stop, or regime loss.

## Best Parameters

- Params(fast_ema=30, slow_ema=100, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=1.0, stop_atr=1.5, max_leverage=1.5)

## Top 10 Candidates

| params | robust_score | full_cagr | full_sharpe | full_calmar | full_max_drawdown | test_2021_2022_cagr | test_2023_now_cagr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Params(fast_ema=30, slow_ema=100, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=1.0, stop_atr=1.5, max_leverage=1.5) | 81.2693 | 0.8403 | 1.3602 | 1.3318 | -0.6309 | 0.3159 | 0.3216 |
| Params(fast_ema=30, slow_ema=100, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=1.0, stop_atr=2.0, max_leverage=1.5) | 81.2693 | 0.8403 | 1.3602 | 1.3318 | -0.6309 | 0.3159 | 0.3216 |
| Params(fast_ema=50, slow_ema=200, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=1.0, stop_atr=1.5, max_leverage=1.5) | 78.9101 | 0.7516 | 1.2805 | 1.1369 | -0.661 | 0.2862 | 0.3589 |
| Params(fast_ema=50, slow_ema=200, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=1.0, stop_atr=2.0, max_leverage=1.5) | 78.3198 | 0.7479 | 1.2767 | 1.1314 | -0.661 | 0.2862 | 0.3489 |
| Params(fast_ema=50, slow_ema=150, entry_breakout=20, exit_breakout=10, vol_window=30, target_vol=1.0, stop_atr=2.0, max_leverage=1.5) | 76.9059 | 0.7239 | 1.3384 | 1.1931 | -0.6068 | 0.0025 | 0.4253 |
| Params(fast_ema=50, slow_ema=150, entry_breakout=20, exit_breakout=10, vol_window=30, target_vol=1.0, stop_atr=1.5, max_leverage=1.5) | 76.9059 | 0.7239 | 1.3384 | 1.1931 | -0.6068 | 0.0025 | 0.4253 |
| Params(fast_ema=30, slow_ema=100, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=0.8, stop_atr=2.0, max_leverage=1.5) | 76.8326 | 0.7539 | 1.3564 | 1.3125 | -0.5744 | 0.2137 | 0.3008 |
| Params(fast_ema=30, slow_ema=100, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=0.8, stop_atr=1.5, max_leverage=1.5) | 76.8326 | 0.7539 | 1.3564 | 1.3125 | -0.5744 | 0.2137 | 0.3008 |
| Params(fast_ema=50, slow_ema=200, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=0.8, stop_atr=1.5, max_leverage=1.5) | 76.7593 | 0.682 | 1.2829 | 1.1079 | -0.6156 | 0.191 | 0.3458 |
| Params(fast_ema=50, slow_ema=200, entry_breakout=20, exit_breakout=20, vol_window=20, target_vol=0.8, stop_atr=2.0, max_leverage=1.5) | 76.2712 | 0.6785 | 1.2787 | 1.1022 | -0.6156 | 0.191 | 0.3358 |

## Per-Period Backtest

| period | start | end | bars | strategy_total_return_pct | strategy_cagr_pct | strategy_sharpe | strategy_calmar | strategy_max_dd_pct | strategy_exposure_pct | strategy_avg_leverage | strategy_trades | strategy_win_rate_pct | buyhold_total_return_pct | buyhold_cagr_pct | buyhold_sharpe | buyhold_calmar | buyhold_max_dd_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_history | 2014-09-17 | 2026-04-01 | 4215 | 113679.66 | 84.03 | 1.36 | 1.33 | -63.09 | 60.08 | 1.4 | 284.0 | 71.48 | 14877.49 | 54.37 | 0.99 | 0.65 | -83.4 |
| 2014_2017 | 2014-09-17 | 2017-12-31 | 1202 | 4398.73 | 218.23 | 2.03 | 5.31 | -41.13 | 78.17 | 1.37 | 114.0 | 87.72 | 2995.42 | 184.03 | 1.8 | 3.01 | -61.06 |
| 2018_2020 | 2018-01-01 | 2020-12-31 | 1096 | 493.73 | 81.15 | 1.37 | 1.29 | -63.09 | 46.94 | 1.38 | 69.0 | 50.72 | 112.35 | 28.56 | 0.72 | 0.35 | -81.53 |
| 2021_2022 | 2021-01-01 | 2022-12-31 | 730 | 72.95 | 31.59 | 0.79 | 0.8 | -39.27 | 34.68 | 1.31 | 42.0 | 52.38 | -43.67 | -24.99 | -0.03 | -0.33 | -76.63 |
| 2023_now | 2023-01-01 | 2026-04-01 | 1187 | 147.31 | 32.16 | 0.82 | 0.81 | -39.7 | 69.53 | 1.48 | 41.0 | 60.98 | 312.01 | 54.66 | 1.15 | 1.1 | -49.74 |

## Research Basis

- Time-series momentum: Moskowitz, Ooi, Pedersen, *Time Series Momentum*.
- Volatility targeting: Moreira, Muir, *Volatility Managed Portfolios*.
- Stylized facts and volatility clustering: Rama Cont, *Empirical properties of asset returns: stylized facts and statistical issues*.
- Crypto trend-following evidence: Rozario et al., *A Decade of Evidence of Trend Following Investing in Cryptocurrencies*.

## Caveat

- This is still a backtest. The search space was intentionally small to reduce overfitting, but no backtest guarantees live results.