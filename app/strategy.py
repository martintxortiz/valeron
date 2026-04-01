from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategyParams:
    fast_ema: int = 16
    slow_ema: int = 64
    entry_breakout: int = 20
    exit_breakout: int = 20


@dataclass(frozen=True)
class SignalDecision:
    bar_timestamp: pd.Timestamp | None
    desired_position: str
    action: str
    close: float | None
    stop_level: float | None
    breakout_high: float | None
    breakout_low: float | None
    fast_ema: float | None
    slow_ema: float | None
    reason: str


DEFAULT_PARAMS = StrategyParams()


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return bars.copy()
    out = bars.copy()
    out.columns = [str(col).lower() for col in out.columns]
    required = ["open", "high", "low", "close"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise RuntimeError(f"Bars missing columns: {missing}")
    return out.sort_index()


def compute_position_frame(bars: pd.DataFrame, params: StrategyParams = DEFAULT_PARAMS) -> pd.DataFrame:
    frame = _normalize_bars(bars)
    min_needed = max(params.slow_ema, params.entry_breakout, params.exit_breakout) + 2
    if len(frame) <= min_needed:
        out = frame.copy()
        out["fast_ema"] = pd.NA
        out["slow_ema"] = pd.NA
        out["breakout_high"] = pd.NA
        out["breakout_low"] = pd.NA
        out["desired_position"] = "flat"
        out["action"] = "hold_flat"
        out["reason"] = "not_enough_bars"
        out["stop_level"] = pd.NA
        return out

    close = frame["close"]
    high = frame["high"]
    low = frame["low"]

    fast = close.ewm(span=params.fast_ema, adjust=False).mean()
    slow = close.ewm(span=params.slow_ema, adjust=False).mean()
    breakout_high = high.rolling(params.entry_breakout).max().shift(1)
    breakout_low = low.rolling(params.exit_breakout).min().shift(1)
    regime = (close > slow) & (fast > slow)

    in_position = False
    desired_positions: list[str] = []
    actions: list[str] = []

    for i in range(len(frame)):
        can_enter = bool(regime.iloc[i] and close.iloc[i] > breakout_high.iloc[i])
        must_exit = bool((close.iloc[i] < breakout_low.iloc[i]) or (not regime.iloc[i]))

        if not in_position and can_enter:
            in_position = True
            action = "enter_long"
        elif in_position and must_exit:
            in_position = False
            action = "exit_long"
        else:
            action = "hold_long" if in_position else "hold_flat"

        desired_positions.append("long" if in_position else "flat")
        actions.append(action)

    out = frame.copy()
    out["fast_ema"] = fast
    out["slow_ema"] = slow
    out["breakout_high"] = breakout_high
    out["breakout_low"] = breakout_low
    out["desired_position"] = desired_positions
    out["action"] = actions
    out["reason"] = actions
    out["stop_level"] = breakout_low
    return out


def compute_signal(bars: pd.DataFrame, params: StrategyParams = DEFAULT_PARAMS) -> SignalDecision:
    frame = compute_position_frame(bars, params)
    if frame.empty:
        return SignalDecision(
            bar_timestamp=None,
            desired_position="flat",
            action="hold_flat",
            close=None,
            stop_level=None,
            breakout_high=None,
            breakout_low=None,
            fast_ema=None,
            slow_ema=None,
            reason="not_enough_bars",
        )

    latest = frame.index[-1]
    return SignalDecision(
        bar_timestamp=latest,
        desired_position=str(frame["desired_position"].iloc[-1]),
        action=str(frame["action"].iloc[-1]),
        close=float(frame["close"].iloc[-1]) if pd.notna(frame["close"].iloc[-1]) else None,
        stop_level=float(frame["stop_level"].iloc[-1]) if pd.notna(frame["stop_level"].iloc[-1]) else None,
        breakout_high=float(frame["breakout_high"].iloc[-1]) if pd.notna(frame["breakout_high"].iloc[-1]) else None,
        breakout_low=float(frame["breakout_low"].iloc[-1]) if pd.notna(frame["breakout_low"].iloc[-1]) else None,
        fast_ema=float(frame["fast_ema"].iloc[-1]) if pd.notna(frame["fast_ema"].iloc[-1]) else None,
        slow_ema=float(frame["slow_ema"].iloc[-1]) if pd.notna(frame["slow_ema"].iloc[-1]) else None,
        reason=str(frame["reason"].iloc[-1]),
    )
