from __future__ import annotations

import pandas as pd

from app.strategy import StrategyParams, compute_signal


def make_bars(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [100] * len(closes),
        },
        index=index,
    )
    return frame


def test_signal_requires_enough_bars():
    bars = make_bars([100 + i for i in range(10)])
    signal = compute_signal(bars, StrategyParams(fast_ema=4, slow_ema=8, entry_breakout=8, exit_breakout=8))
    assert signal.desired_position == "flat"
    assert signal.reason == "not_enough_bars"


def test_signal_enters_after_breakout_with_regime():
    closes = [100] * 20 + [101, 102, 103, 104, 110]
    bars = make_bars(closes)
    signal = compute_signal(bars, StrategyParams(fast_ema=4, slow_ema=8, entry_breakout=5, exit_breakout=5))
    assert signal.desired_position == "long"
    assert signal.action in {"enter_long", "hold_long"}
    assert signal.close == 110


def test_signal_exits_on_breakout_failure():
    closes = [100] * 20 + [101, 102, 103, 104, 110, 108, 107, 90]
    bars = make_bars(closes)
    signal = compute_signal(bars, StrategyParams(fast_ema=4, slow_ema=8, entry_breakout=5, exit_breakout=5))
    assert signal.desired_position == "flat"
    assert signal.action == "exit_long"

