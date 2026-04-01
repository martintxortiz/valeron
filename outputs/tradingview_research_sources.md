# TradingView Research Sources

These links were used to seed the basket of common Pine/TradingView strategy archetypes that were approximated in Python and backtested on `BTC-USD`.

## Core TradingView references

- [TradingView Pine strategies concept docs](https://www.tradingview.com/pine-script-docs/concepts/strategies)
- [TradingView built-ins reference](https://www.tradingview.com/pine-script-docs/language/built-ins)
- [TradingView strategy FAQ](https://www.tradingview.com/pine-script-docs/faq/strategies/)
- [TradingView support article on strategies/backtesting](https://www.tradingview.com/support/solutions/43000562362-what-are-strategies-backtesting-and-forward-testing/)

## Public script search pages used to gather common strategy families

- [Search results for `strategy`](https://www.tradingview.com/scripts/search/strategy/)
- [Search results for `moving average crossover`](https://www.tradingview.com/scripts/search/moving%20average%20crossover/)
- [Search results for `rsi`](https://www.tradingview.com/scripts/search/rsi/)
- [Search results for `bollinger`](https://www.tradingview.com/scripts/search/bollinger/)
- [Search results for `donchian`](https://www.tradingview.com/scripts/search/donchian/)
- [Search results for `supertrend`](https://www.tradingview.com/scripts/search/supertrend/)
- [Search results for `stochastic`](https://www.tradingview.com/scripts/search/stochastic/)
- [Search results for `ichimoku`](https://www.tradingview.com/scripts/search/ichimoku/)
- [Search results for `macd`](https://www.tradingview.com/scripts/search/macd/)

## Approximate strategy basket tested in Python

- Buy and Hold
- SMA 50/200 Trend
- EMA 20/50 Trend
- Triple EMA 10/20/50
- EMA 20/50/200 Stack
- MACD Momentum
- MACD Histogram Reaccel
- RSI Trend Filter
- VWMA 20 Trend
- HMA 55 Trend
- Ichimoku Cloud Trend
- Supertrend 10x3
- ADX DMI Trend
- Keltner Breakout
- Donchian 20/10 Breakout
- Turtle 55/20 Breakout
- RSI Mean Reversion
- Bollinger Mean Reversion
- Bollinger Breakout
- Stochastic Oversold Cross
- Pullback Above 200 SMA
- ATR Trailing Trend

## Important caveat

These are not exact clones of any single public TradingView strategy script. They are standardized Python approximations of recurring strategy types that appear frequently in TradingView’s public Pine ecosystem, so they can be compared fairly on the same BTC dataset.
