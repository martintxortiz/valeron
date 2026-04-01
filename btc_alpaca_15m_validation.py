from __future__ import annotations

import itertools
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import load_config
from app.strategy import StrategyParams, compute_position_frame
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


FEE_PER_TURNOVER = 0.001


def fetch_bars(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    config = load_config()
    client = CryptoHistoricalDataClient(config.api_key, config.api_secret)
    frames = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=20), end)
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=cursor,
            end=chunk_end,
        )
        chunk = client.get_crypto_bars(request).df
        if isinstance(chunk.index, pd.MultiIndex):
            chunk = chunk.xs(symbol, level=0)
        chunk = chunk.rename(columns=str.lower)
        if not chunk.empty:
            frames.append(chunk[["open", "high", "low", "close", "volume"]])
        cursor = chunk_end

    if not frames:
        raise RuntimeError("No Alpaca BTC bars returned.")

    bars = pd.concat(frames).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")]
    return bars


def backtest(frame: pd.DataFrame, risk_per_trade: float, max_alloc_pct: float, min_stop_distance_pct: float) -> dict[str, float]:
    if frame.empty:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "trades": 0.0,
        }
    close = frame["close"]
    stop = frame["stop_level"].astype(float)
    stop_pct = ((close - stop) / close).replace([np.inf, -np.inf], np.nan)
    stop_pct = stop_pct.clip(lower=min_stop_distance_pct).fillna(min_stop_distance_pct)
    desired_long = (frame["desired_position"] == "long").astype(float)
    target_alloc = np.where(desired_long > 0, np.minimum(max_alloc_pct, risk_per_trade / stop_pct), 0.0)
    target_alloc = pd.Series(target_alloc, index=frame.index).fillna(0.0)

    returns = close.pct_change().fillna(0.0)
    strat = target_alloc.shift(1).fillna(0.0) * returns
    strat = strat - target_alloc.diff().abs().fillna(abs(target_alloc.iloc[0])) * FEE_PER_TURNOVER
    equity = (1 + strat).cumprod()

    years = max((frame.index[-1] - frame.index[0]).days / 365.25, 1 / 365.25)
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if equity.iloc[-1] > 0 else -1.0
    vol = strat.std()
    sharpe = float((strat.mean() / vol) * np.sqrt(365.25 * 24 * 4)) if vol and not np.isnan(vol) else 0.0
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min())
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    trades = float(((target_alloc > 0).astype(int).diff().fillna(0) > 0).sum())
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_drawdown": max_drawdown,
        "trades": trades,
    }


def score_rows(df: pd.DataFrame, prefix: str) -> pd.Series:
    scored = pd.DataFrame(
        {
            "cagr": df[f"{prefix}_cagr"].rank(pct=True),
            "sharpe": df[f"{prefix}_sharpe"].rank(pct=True),
            "calmar": df[f"{prefix}_calmar"].rank(pct=True),
            "drawdown": (-df[f"{prefix}_max_drawdown"]).rank(pct=True),
        }
    )
    return scored.mean(axis=1) * 100


def subset(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame.loc[start:end].copy()


def main() -> None:
    config = load_config()
    outdir = Path("outputs")
    outdir.mkdir(exist_ok=True)

    end = datetime.now(UTC)
    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars = fetch_bars(config.symbol, start, end)

    grid = itertools.product(
        [12, 16, 20],
        [48, 64, 96],
        [20, 30],
        [10, 20],
    )

    periods = {
        "full": bars,
        "pre_2021": subset(bars, "2020-01-01", "2020-12-31"),
        "y2021_2022": subset(bars, "2021-01-01", "2022-12-31"),
        "y2023_now": subset(bars, "2023-01-01", str(bars.index[-1].date())),
    }

    rows = []
    for fast, slow, entry, exit_ in grid:
        if fast >= slow:
            continue
        params = StrategyParams(fast_ema=fast, slow_ema=slow, entry_breakout=entry, exit_breakout=exit_)
        frame = compute_position_frame(bars, params)
        row = {"params": str(params), **asdict(params)}
        for name, segment in periods.items():
            segment_frame = frame.reindex(segment.index)
            metrics = backtest(segment_frame, config.risk_per_trade, config.max_alloc_pct, config.min_stop_distance_pct)
            for key, value in metrics.items():
                row[f"{name}_{key}"] = value
        rows.append(row)

    results = pd.DataFrame(rows)
    weights = {"full": 0.4, "pre_2021": 0.2, "y2021_2022": 0.2, "y2023_now": 0.2}
    results["robust_score"] = sum(score_rows(results, prefix) * weight for prefix, weight in weights.items())
    ranked = results.sort_values(["robust_score", "full_calmar", "full_cagr"], ascending=False)
    ranked.to_csv(outdir / "alpaca_btc_15m_validation.csv", index=False)

    best = ranked.iloc[0]
    summary = [
        "# Alpaca BTC 15m Validation",
        "",
        f"- Data start: {bars.index[0]}",
        f"- Data end: {bars.index[-1]}",
        f"- Bars: {len(bars)}",
        "",
        "## Best Parameters",
        "",
        f"- fast_ema={int(best['fast_ema'])}",
        f"- slow_ema={int(best['slow_ema'])}",
        f"- entry_breakout={int(best['entry_breakout'])}",
        f"- exit_breakout={int(best['exit_breakout'])}",
        f"- robust_score={best['robust_score']:.2f}",
        "",
        "## Top 5",
        "",
        ranked[
            [
                "params",
                "robust_score",
                "full_cagr",
                "full_sharpe",
                "full_calmar",
                "pre_2021_cagr",
                "y2021_2022_cagr",
                "y2023_now_cagr",
            ]
        ]
        .head(5)
        .round(4)
        .to_string(index=False),
    ]
    (outdir / "alpaca_btc_15m_validation.md").write_text("\n".join(summary), encoding="utf-8")

    print("\n".join(summary))


if __name__ == "__main__":
    main()
