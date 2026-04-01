from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


TRADING_DAYS = 365.25
SYMBOL = "BTC-USD"
START = "2014-09-17"
FEE = 0.001


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    return close.pct_change().rolling(window).std() * np.sqrt(TRADING_DAYS)


def fetch_data() -> pd.DataFrame:
    df = yf.download(SYMBOL, start=START, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def build_position(df: pd.DataFrame) -> pd.Series:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    fast = ema(close, 30)
    slow = ema(close, 100)
    breakout_high = high.rolling(20).max().shift(1)
    breakout_low = low.rolling(20).min().shift(1)
    size = (1.0 / realized_vol(close, 20).replace(0, np.nan)).clip(0, 1.5).fillna(0)
    regime = (close > slow) & (fast > slow)

    position = pd.Series(0.0, index=df.index)
    in_trade = False
    for i in range(len(df)):
        if not in_trade and regime.iloc[i] and close.iloc[i] > breakout_high.iloc[i]:
            in_trade = True
        elif in_trade and ((close.iloc[i] < breakout_low.iloc[i]) or (not regime.iloc[i])):
            in_trade = False
        position.iloc[i] = float(size.iloc[i]) if in_trade else 0.0
    return position


def backtest(df: pd.DataFrame, position: pd.Series, fee: float = FEE) -> dict[str, float]:
    returns = df["Close"].pct_change().fillna(0.0)
    strat = position.shift(1).fillna(0.0) * returns
    strat = strat - position.diff().abs().fillna(abs(position.iloc[0])) * fee
    equity = (1 + strat).cumprod()
    years = (df.index[-1] - df.index[0]).days / 365.25

    drawdown = equity / equity.cummax() - 1
    vol = strat.std()
    return {
        "total_return_pct": (equity.iloc[-1] - 1) * 100,
        "cagr_pct": (equity.iloc[-1] ** (1 / years) - 1) * 100,
        "sharpe": (strat.mean() / vol) * np.sqrt(TRADING_DAYS) if vol and not np.isnan(vol) else 0.0,
        "max_drawdown_pct": drawdown.min() * 100,
        "exposure_pct": position.mean() * 100,
        "avg_leverage": position[position > 0].mean() if (position > 0).any() else 0.0,
    }


def run() -> None:
    outdir = Path("outputs")
    outdir.mkdir(exist_ok=True)

    df = fetch_data()
    position = build_position(df)
    buy_hold = pd.Series(1.0, index=df.index)

    periods = {
        "full_history": (str(df.index[0].date()), str(df.index[-1].date())),
        "2014_2017": ("2014-09-17", "2017-12-31"),
        "2018_2020": ("2018-01-01", "2020-12-31"),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_now": ("2023-01-01", str(df.index[-1].date())),
    }

    rows = []
    for name, (start, end) in periods.items():
        segment = df.loc[start:end]
        strat_metrics = backtest(segment, position.reindex(segment.index).fillna(0.0))
        hold_metrics = backtest(segment, buy_hold.reindex(segment.index).fillna(1.0), fee=0.0)
        rows.append(
            {
                "period": name,
                "start": str(segment.index[0].date()),
                "end": str(segment.index[-1].date()),
                **{f"strategy_{k}": round(v, 2) for k, v in strat_metrics.items()},
                **{f"buyhold_{k}": round(v, 2) for k, v in hold_metrics.items()},
            }
        )

    report = pd.DataFrame(rows)
    report.to_csv(outdir / "btc_simple_best_strategy_periods.csv", index=False)
    print(report.to_string(index=False))


if __name__ == "__main__":
    run()
