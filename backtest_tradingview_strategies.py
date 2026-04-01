from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


START_DATE = "2017-01-01"
DEFAULT_SYMBOL = "BTC-USD"
TRADING_DAYS = 365.25


@dataclass
class StrategyResult:
    name: str
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    exposure: float
    trades: int
    win_rate: float
    score: float = 0.0


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return rma(tr, length)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    line = fast_ema - slow_ema
    signal_line = ema(line, signal)
    hist = line - signal_line
    return line, signal_line, hist


def bollinger(close: pd.Series, length: int = 20, mult: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    basis = sma(close, length)
    dev = close.rolling(length).std()
    upper = basis + mult * dev
    lower = basis - mult * dev
    return basis, upper, lower


def stochastic(df: pd.DataFrame, k_length: int = 14, d_length: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest = df["Low"].rolling(k_length).min()
    highest = df["High"].rolling(k_length).max()
    k = 100 * (df["Close"] - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_length).mean()
    return k, d


def donchian(df: pd.DataFrame, length: int) -> tuple[pd.Series, pd.Series]:
    upper = df["High"].rolling(length).max()
    lower = df["Low"].rolling(length).min()
    return upper, lower


def vwma(close: pd.Series, volume: pd.Series, length: int) -> pd.Series:
    value = (close * volume).rolling(length).sum()
    total_volume = volume.rolling(length).sum()
    return value / total_volume.replace(0, np.nan)


def hma(close: pd.Series, length: int) -> pd.Series:
    half = max(length // 2, 1)
    root = max(int(math.sqrt(length)), 1)
    wma_half = close.rolling(half).apply(lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)
    wma_full = close.rolling(length).apply(lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)
    raw = 2 * wma_half - wma_full
    return raw.rolling(root).apply(lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)


def adx(df: pd.DataFrame, length: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up_move = df["High"].diff()
    down_move = -df["Low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift(1)).abs(),
            (df["Low"] - df["Close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = rma(tr, length)

    plus_di = 100 * rma(pd.Series(plus_dm, index=df.index), length) / atr_series.replace(0, np.nan)
    minus_di = 100 * rma(pd.Series(minus_dm, index=df.index), length) / atr_series.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx_series = rma(dx, length)
    return plus_di, minus_di, adx_series


def supertrend(df: pd.DataFrame, length: int = 10, multiplier: float = 3.0) -> tuple[pd.Series, pd.Series]:
    atr_series = atr(df, length)
    hl2 = (df["High"] + df["Low"]) / 2
    upper_band = hl2 + multiplier * atr_series
    lower_band = hl2 - multiplier * atr_series

    final_upper = upper_band.copy()
    final_lower = lower_band.copy()
    direction = pd.Series(index=df.index, dtype=float)
    trend = pd.Series(index=df.index, dtype=float)

    direction.iloc[0] = 1
    trend.iloc[0] = lower_band.iloc[0]

    for i in range(1, len(df)):
        if (
            upper_band.iloc[i] < final_upper.iloc[i - 1]
            or df["Close"].iloc[i - 1] > final_upper.iloc[i - 1]
        ):
            final_upper.iloc[i] = upper_band.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if (
            lower_band.iloc[i] > final_lower.iloc[i - 1]
            or df["Close"].iloc[i - 1] < final_lower.iloc[i - 1]
        ):
            final_lower.iloc[i] = lower_band.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if trend.iloc[i - 1] == final_upper.iloc[i - 1]:
            direction.iloc[i] = -1 if df["Close"].iloc[i] <= final_upper.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if df["Close"].iloc[i] >= final_lower.iloc[i] else -1

        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return trend, direction


def crossed_above(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossed_below(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def build_stateful_position(index: pd.Index, entries: pd.Series, exits: pd.Series) -> pd.Series:
    position = pd.Series(0.0, index=index)
    in_trade = False
    for i, ts in enumerate(index):
        if not in_trade and bool(entries.iloc[i]):
            in_trade = True
        elif in_trade and bool(exits.iloc[i]):
            in_trade = False
        position.iloc[i] = 1.0 if in_trade else 0.0
    return position


def ichimoku_signal(df: pd.DataFrame) -> pd.Series:
    high_9 = df["High"].rolling(9).max()
    low_9 = df["Low"].rolling(9).min()
    tenkan = (high_9 + low_9) / 2

    high_26 = df["High"].rolling(26).max()
    low_26 = df["Low"].rolling(26).min()
    kijun = (high_26 + low_26) / 2

    span_a = ((tenkan + kijun) / 2).shift(26)
    high_52 = df["High"].rolling(52).max()
    low_52 = df["Low"].rolling(52).min()
    span_b = ((high_52 + low_52) / 2).shift(26)

    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
    return ((df["Close"] > cloud_top) & (tenkan > kijun) & (cloud_top > cloud_bottom)).astype(float)


def build_strategies(df: pd.DataFrame) -> dict[str, pd.Series]:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"].replace(0, np.nan)

    sma_50 = sma(close, 50)
    sma_200 = sma(close, 200)
    ema_10 = ema(close, 10)
    ema_20 = ema(close, 20)
    ema_50 = ema(close, 50)
    ema_100 = ema(close, 100)
    ema_200 = ema(close, 200)
    vwma_20 = vwma(close, volume.ffill().fillna(0), 20)
    hma_55 = hma(close, 55)
    rsi_14 = rsi(close, 14)
    macd_line, macd_signal, macd_hist = macd(close)
    bb_basis, bb_upper, bb_lower = bollinger(close)
    stoch_k, stoch_d = stochastic(df)
    dc_upper_20, dc_lower_10 = donchian(df, 20)[0], donchian(df, 10)[1]
    dc_upper_55 = donchian(df, 55)[0]
    dc_lower_20 = donchian(df, 20)[1]
    atr_20 = atr(df, 20)
    kel_upper = ema_20 + 2 * atr_20
    plus_di, minus_di, adx_14 = adx(df)
    st_line, st_dir = supertrend(df, 10, 3.0)

    strategies: dict[str, pd.Series] = {}
    strategies["Buy and Hold"] = pd.Series(1.0, index=df.index)
    strategies["SMA 50/200 Trend"] = (sma_50 > sma_200).astype(float)
    strategies["EMA 20/50 Trend"] = (ema_20 > ema_50).astype(float)
    strategies["Triple EMA 10/20/50"] = ((ema_10 > ema_20) & (ema_20 > ema_50) & (close > ema_50)).astype(float)
    strategies["EMA 20/50/200 Stack"] = ((ema_20 > ema_50) & (ema_50 > ema_200) & (close > ema_20)).astype(float)
    strategies["MACD Momentum"] = ((macd_line > macd_signal) & (macd_line > 0) & (close > sma_200)).astype(float)
    strategies["MACD Histogram Reaccel"] = ((macd_hist > 0) & (macd_hist > macd_hist.shift(1)) & (close > ema_100)).astype(float)
    strategies["RSI Trend Filter"] = ((rsi_14 > 55) & (close > sma_200)).astype(float)
    strategies["VWMA 20 Trend"] = ((close > vwma_20) & (ema_20 > ema_50)).astype(float)
    strategies["HMA 55 Trend"] = ((close > hma_55) & (hma_55 > hma_55.shift(1))).astype(float)
    strategies["Ichimoku Cloud Trend"] = ichimoku_signal(df)
    strategies["Supertrend 10x3"] = ((st_dir > 0) & (close > st_line)).astype(float)
    strategies["ADX DMI Trend"] = ((plus_di > minus_di) & (adx_14 > 20) & (close > ema_50)).astype(float)
    strategies["Keltner Breakout"] = build_stateful_position(
        df.index,
        close > kel_upper,
        close < ema_20,
    )
    strategies["Donchian 20/10 Breakout"] = build_stateful_position(
        df.index,
        close > dc_upper_20.shift(1),
        close < dc_lower_10.shift(1),
    )
    strategies["Turtle 55/20 Breakout"] = build_stateful_position(
        df.index,
        close > dc_upper_55.shift(1),
        close < dc_lower_20.shift(1),
    )
    strategies["RSI Mean Reversion"] = build_stateful_position(
        df.index,
        rsi_14 < 30,
        rsi_14 > 55,
    )
    strategies["Bollinger Mean Reversion"] = build_stateful_position(
        df.index,
        close < bb_lower,
        close > bb_basis,
    )
    strategies["Bollinger Breakout"] = build_stateful_position(
        df.index,
        close > bb_upper,
        close < bb_basis,
    )
    strategies["Stochastic Oversold Cross"] = build_stateful_position(
        df.index,
        crossed_above(stoch_k, stoch_d) & (stoch_k < 20) & (stoch_d < 20),
        crossed_below(stoch_k, stoch_d) | (stoch_k > 80),
    )
    strategies["Pullback Above 200 SMA"] = build_stateful_position(
        df.index,
        crossed_above(close, ema_20) & (close > sma_200),
        close < ema_50,
    )
    strategies["ATR Trailing Trend"] = ((close > (ema_50 + 0.5 * atr_20)) & (ema_20 > ema_50)).astype(float)

    return strategies


def extract_trade_returns(close: pd.Series, position: pd.Series, fee: float) -> list[float]:
    entries = position.diff().fillna(position.iloc[0]) > 0
    exits = position.diff() < 0

    entry_dates = list(close.index[entries])
    exit_dates = list(close.index[exits])
    returns: list[float] = []
    exit_ptr = 0

    for entry_date in entry_dates:
        while exit_ptr < len(exit_dates) and exit_dates[exit_ptr] <= entry_date:
            exit_ptr += 1
        if exit_ptr >= len(exit_dates):
            break
        exit_date = exit_dates[exit_ptr]
        gross = close.loc[exit_date] / close.loc[entry_date] - 1
        net = gross - (2 * fee)
        returns.append(net)
        exit_ptr += 1
    return returns


def backtest(df: pd.DataFrame, position: pd.Series, fee: float) -> dict[str, float]:
    position = position.fillna(0).clip(0, 1)
    asset_returns = df["Close"].pct_change().fillna(0)
    strategy_returns = position.shift(1).fillna(0) * asset_returns
    turnover = position.diff().abs().fillna(position.iloc[0])
    strategy_returns = strategy_returns - turnover * fee
    equity = (1 + strategy_returns).cumprod()

    years = max((df.index[-1] - df.index[0]).days / 365.25, 1 / 365.25)
    total_return = equity.iloc[-1] - 1
    cagr = equity.iloc[-1] ** (1 / years) - 1 if equity.iloc[-1] > 0 else -1

    vol = strategy_returns.std()
    sharpe = (strategy_returns.mean() / vol) * np.sqrt(TRADING_DAYS) if vol and not np.isnan(vol) else 0.0

    downside = strategy_returns[strategy_returns < 0].std()
    sortino = (
        (strategy_returns.mean() / downside) * np.sqrt(TRADING_DAYS)
        if downside and not np.isnan(downside)
        else 0.0
    )

    drawdown = equity / equity.cummax() - 1
    max_drawdown = drawdown.min()
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else np.nan

    trade_returns = extract_trade_returns(df["Close"], position, fee)
    trades = len(trade_returns)
    win_rate = float(np.mean([r > 0 for r in trade_returns])) if trade_returns else 0.0
    exposure = position.mean()

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar if not np.isnan(calmar) else 0.0,
        "exposure": exposure,
        "trades": trades,
        "win_rate": win_rate,
    }


def percentile_score(results: pd.DataFrame) -> pd.Series:
    components = {
        "total_return": results["total_return"].rank(pct=True),
        "cagr": results["cagr"].rank(pct=True),
        "sharpe": results["sharpe"].rank(pct=True),
        "sortino": results["sortino"].rank(pct=True),
        "max_drawdown": (-results["max_drawdown"]).rank(pct=True),
        "calmar": results["calmar"].rank(pct=True),
        "win_rate": results["win_rate"].rank(pct=True),
    }
    score = pd.DataFrame(components).mean(axis=1) * 100
    return score.round(2)


def fetch_data(symbol: str, start: str) -> pd.DataFrame:
    data = yf.download(symbol, start=start, auto_adjust=False, progress=False)
    if data.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise RuntimeError(f"Missing expected columns: {missing}")
    return data[required].dropna()


def format_results(results: pd.DataFrame) -> pd.DataFrame:
    pretty = results.copy()
    for col in ["total_return", "cagr", "sortino", "max_drawdown", "calmar", "exposure", "win_rate"]:
        if col in pretty:
            pretty[col] = pretty[col].astype(float)
    pretty["total_return_pct"] = pretty["total_return"] * 100
    pretty["cagr_pct"] = pretty["cagr"] * 100
    pretty["max_drawdown_pct"] = pretty["max_drawdown"] * 100
    pretty["exposure_pct"] = pretty["exposure"] * 100
    pretty["win_rate_pct"] = pretty["win_rate"] * 100
    cols = [
        "score",
        "total_return_pct",
        "cagr_pct",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown_pct",
        "exposure_pct",
        "trades",
        "win_rate_pct",
    ]
    pretty = pretty[cols].round(2)
    return pretty


def markdown_table(df: pd.DataFrame) -> str:
    headers = ["Strategy"] + list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for idx, row in df.iterrows():
        values = [str(idx)] + [str(row[col]) for col in df.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest common TradingView/Pine-style strategies on Bitcoin.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--start", default=START_DATE)
    parser.add_argument("--fee", type=float, default=0.001, help="Per-side trading cost, e.g. 0.001 = 0.10%%")
    parser.add_argument("--outdir", default="outputs")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = fetch_data(args.symbol, args.start)
    strategies = build_strategies(df)

    rows: list[StrategyResult] = []
    for name, position in strategies.items():
        metrics = backtest(df, position, args.fee)
        rows.append(StrategyResult(name=name, **metrics))

    results = pd.DataFrame([vars(r) for r in rows]).set_index("name")
    results["score"] = percentile_score(results)
    results = results.sort_values(["score", "cagr", "sharpe"], ascending=False)

    raw_path = outdir / "btc_strategy_ranking_raw.csv"
    pretty_path = outdir / "btc_strategy_ranking.csv"
    summary_path = outdir / "btc_strategy_summary.md"

    results.to_csv(raw_path)
    pretty = format_results(results)
    pretty.to_csv(pretty_path)

    top5 = pretty.head(5)
    lines = [
        f"# BTC Strategy Ranking ({args.symbol})",
        "",
        f"- Data start: {df.index[0].date()}",
        f"- Data end: {df.index[-1].date()}",
        f"- Bars: {len(df)}",
        f"- Fee per side: {args.fee:.4%}",
        f"- Strategies tested: {len(results)}",
        "",
        "## Top 5",
        "",
        markdown_table(top5),
        "",
        "## Notes",
        "",
        "- These are Python approximations of common TradingView/Pine strategy archetypes, not exact clones of individual public scripts.",
        "- Signals are lagged one bar in the backtest to reduce lookahead bias.",
        "- Ranking score is the average percentile rank across return, CAGR, Sharpe, Sortino, Calmar, drawdown, and win rate.",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved raw metrics to: {raw_path}")
    print(f"Saved formatted ranking to: {pretty_path}")
    print(f"Saved summary markdown to: {summary_path}")
    print()
    print(pretty.head(10).to_string())


if __name__ == "__main__":
    main()
