from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.broker import AccountSnapshot, AlpacaBroker, OpenOrderSnapshot, PositionSnapshot
from app.config import load_config
from app.strategy import SignalDecision, compute_signal


logger = logging.getLogger("alpaca-btc-bot")


@dataclass(frozen=True)
class OrderIntent:
    side: str
    symbol: str
    qty: float | None
    notional: float | None
    reason: str
    client_order_id: str


@dataclass(frozen=True)
class RuntimeState:
    last_processed_bar: str | None = None
    last_desired_position: str = "flat"
    last_submitted_order_id: str | None = None
    last_submitted_client_order_id: str | None = None
    last_stop_level: float | None = None
    broker_has_position: bool = False
    broker_has_open_order: bool = False


@dataclass(frozen=True)
class CycleResult:
    status: str
    action: str
    desired_position: str
    message: str
    order_client_id: str | None = None
    order_id: str | None = None


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(message)s")


def log_event(event: str, **fields) -> None:
    payload = {"ts": datetime.now(UTC).isoformat(), "event": event, **fields}
    logger.info(json.dumps(payload, default=str))


def load_snapshot(path: Path) -> RuntimeState:
    if not path.exists():
        return RuntimeState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeState(**data)


def save_snapshot(path: Path, state: RuntimeState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def latest_closed_bar_time(now: datetime | None = None) -> pd.Timestamp:
    now = now or datetime.now(UTC)
    ts = pd.Timestamp(now).tz_convert("UTC") if pd.Timestamp(now).tzinfo else pd.Timestamp(now, tz="UTC")
    return ts.floor("15min") - pd.Timedelta(minutes=15)


def reconcile_state(
    account: AccountSnapshot,
    position: PositionSnapshot | None,
    orders: list[OpenOrderSnapshot],
    snapshot: RuntimeState,
) -> RuntimeState:
    del account
    latest_open = orders[0] if orders else None
    return RuntimeState(
        last_processed_bar=snapshot.last_processed_bar,
        last_desired_position=snapshot.last_desired_position,
        last_submitted_order_id=latest_open.order_id if latest_open else snapshot.last_submitted_order_id,
        last_submitted_client_order_id=latest_open.client_order_id if latest_open else snapshot.last_submitted_client_order_id,
        last_stop_level=snapshot.last_stop_level,
        broker_has_position=position is not None and position.qty > 0,
        broker_has_open_order=bool(orders),
    )


def _client_order_id(symbol: str, side: str, bar_timestamp: pd.Timestamp) -> str:
    compact_symbol = symbol.replace("/", "").lower()
    return f"{compact_symbol}-{side}-{bar_timestamp.strftime('%Y%m%d%H%M')}"


def compute_target_order(
    account: AccountSnapshot,
    position: PositionSnapshot | None,
    signal: SignalDecision,
) -> OrderIntent | None:
    config = load_config()

    if signal.bar_timestamp is None or signal.close is None:
        return None

    if signal.desired_position == "flat":
        if position is None or position.qty <= config.position_qty_tolerance:
            return None
        return OrderIntent(
            side="sell",
            symbol=config.symbol,
            qty=position.qty,
            notional=None,
            reason=signal.reason,
            client_order_id=_client_order_id(config.symbol, "sell", signal.bar_timestamp),
        )

    if position is not None and position.qty > config.position_qty_tolerance:
        return None

    if signal.stop_level is None:
        return None

    minimum_stop = signal.close * config.min_stop_distance_pct
    stop_distance = max(signal.close - signal.stop_level, minimum_stop)
    if stop_distance <= 0:
        return None

    risk_budget = account.equity * config.risk_per_trade
    risk_based_notional = (risk_budget / stop_distance) * signal.close
    safe_cash = min(account.cash, account.buying_power) * config.max_alloc_pct
    notional = min(risk_based_notional, safe_cash)

    if notional < config.min_order_notional:
        return None

    return OrderIntent(
        side="buy",
        symbol=config.symbol,
        qty=None,
        notional=round(notional, 2),
        reason=signal.reason,
        client_order_id=_client_order_id(config.symbol, "buy", signal.bar_timestamp),
    )


def run_once(now: datetime | None = None) -> CycleResult:
    config = load_config()
    configure_logging(config.log_level)
    broker = AlpacaBroker(config)

    now = now or datetime.now(UTC)
    snapshot = load_snapshot(config.state_path)
    account = broker.get_account_snapshot()
    position = broker.get_position(config.symbol)
    orders = broker.list_open_orders(config.symbol)
    runtime_state = reconcile_state(account, position, orders, snapshot)

    if runtime_state.broker_has_open_order:
        save_snapshot(config.state_path, runtime_state)
        log_event("cycle_blocked_open_order", symbol=config.symbol, open_orders=len(orders))
        return CycleResult(
            status="ok",
            action="blocked_open_order",
            desired_position=snapshot.last_desired_position,
            message="Open order exists; skipping new submissions.",
        )

    bars = broker.get_crypto_bars(config.symbol, config.history_limit, now=now)
    closed_bar = latest_closed_bar_time(now)
    bars = bars.loc[bars.index <= closed_bar]
    signal = compute_signal(bars)

    if signal.bar_timestamp is None:
        save_snapshot(config.state_path, runtime_state)
        return CycleResult(status="ok", action="no_signal", desired_position="flat", message="No bars available.")

    if runtime_state.last_processed_bar == signal.bar_timestamp.isoformat():
        refreshed = RuntimeState(
            last_processed_bar=runtime_state.last_processed_bar,
            last_desired_position=signal.desired_position,
            last_submitted_order_id=runtime_state.last_submitted_order_id,
            last_submitted_client_order_id=runtime_state.last_submitted_client_order_id,
            last_stop_level=signal.stop_level,
            broker_has_position=runtime_state.broker_has_position,
            broker_has_open_order=False,
        )
        save_snapshot(config.state_path, refreshed)
        log_event("cycle_no_new_bar", symbol=config.symbol, bar_timestamp=signal.bar_timestamp.isoformat())
        return CycleResult(
            status="ok",
            action="no_new_bar",
            desired_position=signal.desired_position,
            message="No new closed bar since last processed cycle.",
        )

    intent = compute_target_order(account, position, signal)
    updated_state = RuntimeState(
        last_processed_bar=signal.bar_timestamp.isoformat(),
        last_desired_position=signal.desired_position,
        last_submitted_order_id=runtime_state.last_submitted_order_id,
        last_submitted_client_order_id=runtime_state.last_submitted_client_order_id,
        last_stop_level=signal.stop_level,
        broker_has_position=position is not None and position.qty > config.position_qty_tolerance,
        broker_has_open_order=False,
    )

    if intent is None:
        save_snapshot(config.state_path, updated_state)
        log_event(
            "cycle_hold",
            symbol=config.symbol,
            desired_position=signal.desired_position,
            signal_reason=signal.reason,
            close=signal.close,
        )
        return CycleResult(
            status="ok",
            action="hold",
            desired_position=signal.desired_position,
            message="No order required for current broker state.",
        )

    if config.dry_run:
        dry_state = RuntimeState(
            last_processed_bar=updated_state.last_processed_bar,
            last_desired_position=updated_state.last_desired_position,
            last_submitted_order_id=None,
            last_submitted_client_order_id=intent.client_order_id,
            last_stop_level=updated_state.last_stop_level,
            broker_has_position=updated_state.broker_has_position,
            broker_has_open_order=False,
        )
        save_snapshot(config.state_path, dry_state)
        log_event("cycle_dry_run_order", symbol=config.symbol, side=intent.side, qty=intent.qty, notional=intent.notional)
        return CycleResult(
            status="ok",
            action="dry_run_order",
            desired_position=signal.desired_position,
            message="Dry run mode; order was not submitted.",
            order_client_id=intent.client_order_id,
        )

    if intent.side == "sell":
        order = broker.submit_market_sell_qty(intent.symbol, intent.qty or 0.0, intent.client_order_id)
    else:
        order = broker.submit_market_buy_notional(intent.symbol, intent.notional or 0.0, intent.client_order_id)

    refreshed_account = broker.get_account_snapshot()
    refreshed_position = broker.get_position(config.symbol)
    refreshed_orders = broker.list_open_orders(config.symbol)
    reconciled = reconcile_state(refreshed_account, refreshed_position, refreshed_orders, updated_state)
    final_state = RuntimeState(
        last_processed_bar=updated_state.last_processed_bar,
        last_desired_position=updated_state.last_desired_position,
        last_submitted_order_id=str(getattr(order, "id", "")) or reconciled.last_submitted_order_id,
        last_submitted_client_order_id=intent.client_order_id,
        last_stop_level=updated_state.last_stop_level,
        broker_has_position=reconciled.broker_has_position,
        broker_has_open_order=reconciled.broker_has_open_order,
    )
    save_snapshot(config.state_path, final_state)
    log_event("cycle_submitted_order", symbol=config.symbol, side=intent.side, client_order_id=intent.client_order_id)
    return CycleResult(
        status="ok",
        action="submitted_order",
        desired_position=signal.desired_position,
        message="Order submitted successfully.",
        order_client_id=intent.client_order_id,
        order_id=str(getattr(order, "id", "")),
    )


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)
    log_event("bot_start", symbol=config.symbol, dry_run=config.dry_run, poll_seconds=config.poll_seconds)
    while True:
        try:
            result = run_once()
            log_event("cycle_result", action=result.action, message=result.message, desired_position=result.desired_position)
        except Exception as exc:
            log_event("cycle_error", error=str(exc))
        time.sleep(config.poll_seconds)


if __name__ == "__main__":
    main()
