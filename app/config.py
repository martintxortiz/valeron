from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_key: str
    api_secret: str
    paper: bool
    symbol: str
    timeframe: str
    risk_per_trade: float
    max_alloc_pct: float
    poll_seconds: int
    log_level: str
    dry_run: bool
    state_path: Path
    history_limit: int
    position_qty_tolerance: float
    min_order_notional: float
    min_stop_distance_pct: float
    crypto_data_feed: str = "us"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def load_config() -> Config:
    load_dotenv()

    api_key = os.getenv("APCA_API_KEY_ID") or os.getenv("key")
    api_secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("secret")
    if not api_key or not api_secret:
        raise RuntimeError("Missing Alpaca credentials. Set key/secret or APCA_API_KEY_ID/APCA_API_SECRET_KEY in .env.")

    symbol = os.getenv("SYMBOL", "BTC/USD").strip().upper()
    timeframe = os.getenv("BAR_TIMEFRAME", "15Min").strip()
    if timeframe != "15Min":
        raise RuntimeError(f"Unsupported BAR_TIMEFRAME={timeframe}. This bot currently supports only 15Min.")

    state_path = Path(os.getenv("STATE_PATH", "state/runtime_state.json"))
    return Config(
        api_key=api_key,
        api_secret=api_secret,
        paper=_env_bool("APCA_PAPER", True),
        symbol=symbol,
        timeframe=timeframe,
        risk_per_trade=_env_float("RISK_PER_TRADE", 0.01),
        max_alloc_pct=_env_float("MAX_ALLOC_PCT", 0.95),
        poll_seconds=_env_int("POLL_SECONDS", 60),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        dry_run=_env_bool("DRY_RUN", True),
        state_path=state_path,
        history_limit=_env_int("HISTORY_LIMIT", 500),
        position_qty_tolerance=_env_float("POSITION_QTY_TOLERANCE", 1e-8),
        min_order_notional=_env_float("MIN_ORDER_NOTIONAL", 10.0),
        min_stop_distance_pct=_env_float("MIN_STOP_DISTANCE_PCT", 0.002),
    )

