from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


TRADING_DAYS = 365.25


@dataclass(frozen=True)
class Params:
    fast_ema: int
    slow_ema: int
    entry_breakout: int
    exit_breakout: int
    vol_window: int
    target_vol: float
    stop_atr: float
    max_leverage: float


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False).mean()


def atr(df: pd.DataFrame, length: int = 20) -> pd.Series:
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


def realized_vol(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change().rolling(window).std() * np.sqrt(TRADING_DAYS)


def fetch_data(symbol: str, start: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if df.empty:
        raise RuntimeError(f"No data for {symbol}")
    return df


def position_from_params(df: pd.DataFrame, p: Params) -> pd.Series:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    fast = ema(close, p.fast_ema)
    slow = ema(close, p.slow_ema)
    atr_20 = atr(df, 20)
    vol = realized_vol(close, p.vol_window)

    entry_level = high.rolling(p.entry_breakout).max().shift(1)
    exit_level = low.rolling(p.exit_breakout).min().shift(1)
    stop_line = fast - p.stop_atr * atr_20
    regime = (close > slow) & (fast > slow)
    size = (p.target_vol / vol.replace(0, np.nan)).clip(lower=0, upper=p.max_leverage).fillna(0)

    position = pd.Series(0.0, index=df.index)
    in_trade = False

    for i, ts in enumerate(df.index):
        can_enter = bool(regime.iloc[i] and close.iloc[i] > entry_level.iloc[i])
        must_exit = bool(
            (close.iloc[i] < exit_level.iloc[i])
            or (close.iloc[i] < stop_line.iloc[i])
            or (not regime.iloc[i])
        )

        if not in_trade and can_enter:
            in_trade = True
        elif in_trade and must_exit:
            in_trade = False

        position.iloc[i] = float(size.iloc[i]) if in_trade else 0.0

    return position


def extract_trade_returns(close: pd.Series, position: pd.Series, fee: float) -> list[float]:
    entered = position.diff().fillna(position.iloc[0]) > 0
    exited = position.diff() < 0
    entry_dates = list(close.index[entered])
    exit_dates = list(close.index[exited])

    trade_returns: list[float] = []
    j = 0
    for entry_date in entry_dates:
        while j < len(exit_dates) and exit_dates[j] <= entry_date:
            j += 1
        if j >= len(exit_dates):
            break
        exit_date = exit_dates[j]
        gross = close.loc[exit_date] / close.loc[entry_date] - 1
        net = gross - 2 * fee
        trade_returns.append(float(net))
        j += 1
    return trade_returns


def backtest(df: pd.DataFrame, position: pd.Series, fee: float) -> dict[str, float]:
    position = position.fillna(0.0)
    returns = df["Close"].pct_change().fillna(0.0)
    strat = position.shift(1).fillna(0.0) * returns
    strat = strat - position.diff().abs().fillna(abs(position.iloc[0])) * fee
    equity = (1 + strat).cumprod()

    years = max((df.index[-1] - df.index[0]).days / 365.25, 1 / 365.25)
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if equity.iloc[-1] > 0 else -1.0
    vol = strat.std()
    sharpe = float((strat.mean() / vol) * np.sqrt(TRADING_DAYS)) if vol and not np.isnan(vol) else 0.0
    downside = strat[strat < 0].std()
    sortino = float((strat.mean() / downside) * np.sqrt(TRADING_DAYS)) if downside and not np.isnan(downside) else 0.0
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min())
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    trades = extract_trade_returns(df["Close"], position, fee)
    win_rate = float(np.mean([x > 0 for x in trades])) if trades else 0.0

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "exposure": float(position.mean()),
        "avg_leverage": float(position[position > 0].mean()) if (position > 0).any() else 0.0,
        "trades": float(len(trades)),
        "win_rate": win_rate,
    }


def subset(df: pd.DataFrame, start: str, end: str | None = None) -> pd.DataFrame:
    out = df.loc[start:end].copy()
    return out


def strategy_score(df: pd.DataFrame) -> pd.Series:
    pieces = {
        "cagr": df["cagr"].rank(pct=True),
        "sharpe": df["sharpe"].rank(pct=True),
        "sortino": df["sortino"].rank(pct=True),
        "calmar": df["calmar"].rank(pct=True),
        "drawdown": (-df["max_drawdown"]).rank(pct=True),
        "win_rate": df["win_rate"].rank(pct=True),
    }
    return pd.DataFrame(pieces).mean(axis=1) * 100


def search_best_params(df: pd.DataFrame, fee: float) -> tuple[Params, pd.DataFrame]:
    grid = list(
        itertools.product(
            [30, 50],
            [100, 150, 200],
            [20, 50, 80],
            [10, 20],
            [20, 30],
            [0.60, 0.80, 1.00],
            [1.5, 2.0],
            [1.0, 1.5],
        )
    )

    train = subset(df, str(df.index[0].date()), "2020-12-31")
    test1 = subset(df, "2021-01-01", "2022-12-31")
    test2 = subset(df, "2023-01-01", str(df.index[-1].date()))
    periods = {
        "full": df,
        "train": train,
        "test_2021_2022": test1,
        "test_2023_now": test2,
    }

    rows = []
    for values in grid:
        p = Params(*values)
        full_position = position_from_params(df, p)

        row = {"params": p}
        for name, period_df in periods.items():
            if len(period_df) < max(p.slow_ema, p.entry_breakout) + 5:
                metrics = {k: np.nan for k in ["total_return", "cagr", "sharpe", "sortino", "max_drawdown", "calmar", "exposure", "avg_leverage", "trades", "win_rate"]}
            else:
                pos = full_position.reindex(period_df.index).fillna(0.0)
                metrics = backtest(period_df, pos, fee)
            for k, v in metrics.items():
                row[f"{name}_{k}"] = v
        rows.append(row)

    results = pd.DataFrame(rows)

    period_scores = []
    weights = {"full": 0.4, "train": 0.2, "test_2021_2022": 0.2, "test_2023_now": 0.2}
    for period_name, weight in weights.items():
        cols = {
            "cagr": f"{period_name}_cagr",
            "sharpe": f"{period_name}_sharpe",
            "sortino": f"{period_name}_sortino",
            "calmar": f"{period_name}_calmar",
            "max_drawdown": f"{period_name}_max_drawdown",
            "win_rate": f"{period_name}_win_rate",
        }
        scored = results.rename(columns={v: k for k, v in cols.items()})[list(cols.keys())]
        score = strategy_score(scored) * weight
        period_scores.append(score)

    results["robust_score"] = sum(period_scores)
    results["min_cagr_test"] = results[["test_2021_2022_cagr", "test_2023_now_cagr"]].min(axis=1)
    results["full_trades"] = results["full_trades"].fillna(0)
    filtered = results[(results["full_trades"] >= 5) & (results["min_cagr_test"] > -0.20)].copy()
    best_row = filtered.sort_values(
        ["robust_score", "full_calmar", "full_sharpe", "full_cagr"],
        ascending=False,
    ).iloc[0]

    return best_row["params"], results.sort_values("robust_score", ascending=False)


def period_report(df: pd.DataFrame, position: pd.Series, fee: float) -> pd.DataFrame:
    periods = {
        "full_history": (str(df.index[0].date()), str(df.index[-1].date())),
        "2014_2017": ("2014-09-17", "2017-12-31"),
        "2018_2020": ("2018-01-01", "2020-12-31"),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_now": ("2023-01-01", str(df.index[-1].date())),
    }
    rows = []
    buy_hold = pd.Series(1.0, index=df.index)
    for label, (start, end) in periods.items():
        segment = subset(df, start, end)
        if segment.empty:
            continue
        seg_pos = position.reindex(segment.index).fillna(0.0)
        strat = backtest(segment, seg_pos, fee)
        hold = backtest(segment, buy_hold.reindex(segment.index).fillna(1.0), fee=0.0)
        rows.append(
            {
                "period": label,
                "start": str(segment.index[0].date()),
                "end": str(segment.index[-1].date()),
                "bars": len(segment),
                "strategy_total_return_pct": strat["total_return"] * 100,
                "strategy_cagr_pct": strat["cagr"] * 100,
                "strategy_sharpe": strat["sharpe"],
                "strategy_calmar": strat["calmar"],
                "strategy_max_dd_pct": strat["max_drawdown"] * 100,
                "strategy_exposure_pct": strat["exposure"] * 100,
                "strategy_avg_leverage": strat["avg_leverage"],
                "strategy_trades": strat["trades"],
                "strategy_win_rate_pct": strat["win_rate"] * 100,
                "buyhold_total_return_pct": hold["total_return"] * 100,
                "buyhold_cagr_pct": hold["cagr"] * 100,
                "buyhold_sharpe": hold["sharpe"],
                "buyhold_calmar": hold["calmar"],
                "buyhold_max_dd_pct": hold["max_drawdown"] * 100,
            }
        )
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        vals = [str(row[h]) for h in headers]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple first-principles BTC strategy search and backtest.")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--start", default="2014-09-17")
    parser.add_argument("--fee", type=float, default=0.001, help="Per-side fee, e.g. 0.001 = 0.10%%")
    parser.add_argument("--outdir", default="outputs")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = fetch_data(args.symbol, args.start)
    best_params, search_results = search_best_params(df, args.fee)
    best_position = position_from_params(df, best_params)
    reports = period_report(df, best_position, args.fee).round(2)

    search_export = search_results.copy()
    search_export["params"] = search_export["params"].astype(str)
    search_export.to_csv(outdir / "btc_first_principles_search.csv", index=False)
    reports.to_csv(outdir / "btc_first_principles_periods.csv", index=False)

    top_candidates = search_results.head(10).copy()
    top_candidates["params"] = top_candidates["params"].astype(str)
    top_candidates = top_candidates[
        [
            "params",
            "robust_score",
            "full_cagr",
            "full_sharpe",
            "full_calmar",
            "full_max_drawdown",
            "test_2021_2022_cagr",
            "test_2023_now_cagr",
        ]
    ].round(4)

    summary = [
        "# BTC First-Principles Strategy",
        "",
        "## Idea",
        "",
        "- Trend persistence: only participate when short trend is above long trend and price is above the long trend.",
        "- Convexity: require an n-day breakout so we are paying for strength, not guessing bottoms.",
        "- Volatility clustering: scale exposure inversely with realized volatility instead of using fixed size.",
        "- Fat-tail defense: exit on either a shorter breakout failure, a volatility-adjusted stop, or regime loss.",
        "",
        "## Best Parameters",
        "",
        f"- {best_params}",
        "",
        "## Top 10 Candidates",
        "",
        markdown_table(top_candidates),
        "",
        "## Per-Period Backtest",
        "",
        markdown_table(reports),
        "",
        "## Research Basis",
        "",
        "- Time-series momentum: Moskowitz, Ooi, Pedersen, *Time Series Momentum*.",
        "- Volatility targeting: Moreira, Muir, *Volatility Managed Portfolios*.",
        "- Stylized facts and volatility clustering: Rama Cont, *Empirical properties of asset returns: stylized facts and statistical issues*.",
        "- Crypto trend-following evidence: Rozario et al., *A Decade of Evidence of Trend Following Investing in Cryptocurrencies*.",
        "",
        "## Caveat",
        "",
        "- This is still a backtest. The search space was intentionally small to reduce overfitting, but no backtest guarantees live results.",
    ]
    (outdir / "btc_first_principles_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print("Best parameters:")
    print(best_params)
    print()
    print(reports.to_string(index=False))
    print()
    print(f"Saved search grid to: {outdir / 'btc_first_principles_search.csv'}")
    print(f"Saved period report to: {outdir / 'btc_first_principles_periods.csv'}")
    print(f"Saved summary to: {outdir / 'btc_first_principles_summary.md'}")


if __name__ == "__main__":
    main()
