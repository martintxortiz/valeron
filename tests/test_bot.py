from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from app.bot import RuntimeState, compute_target_order, latest_closed_bar_time, reconcile_state, run_once
from app.broker import AccountSnapshot, OpenOrderSnapshot, PositionSnapshot
from app.strategy import SignalDecision


def test_compute_target_order_respects_risk_and_cash(monkeypatch):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    monkeypatch.setenv("RISK_PER_TRADE", "0.01")
    monkeypatch.setenv("MAX_ALLOC_PCT", "0.95")
    monkeypatch.setenv("MIN_ORDER_NOTIONAL", "10")
    monkeypatch.setenv("MIN_STOP_DISTANCE_PCT", "0.002")

    account = AccountSnapshot(equity=1000, cash=400, buying_power=800)
    signal = SignalDecision(
        bar_timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        desired_position="long",
        action="enter_long",
        close=100.0,
        stop_level=99.0,
        breakout_high=100.0,
        breakout_low=99.0,
        fast_ema=101.0,
        slow_ema=99.0,
        reason="enter_long",
    )

    intent = compute_target_order(account, None, signal)
    assert intent is not None
    assert intent.side == "buy"
    assert intent.notional == pytest.approx(380.0, rel=1e-6)


def test_compute_target_order_blocks_additional_buy(monkeypatch):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    account = AccountSnapshot(equity=1000, cash=1000, buying_power=1000)
    position = PositionSnapshot(symbol="BTC/USD", qty=0.01, market_value=1000, avg_entry_price=100000)
    signal = SignalDecision(
        bar_timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        desired_position="long",
        action="hold_long",
        close=100.0,
        stop_level=99.0,
        breakout_high=100.0,
        breakout_low=99.0,
        fast_ema=101.0,
        slow_ema=99.0,
        reason="hold_long",
    )
    assert compute_target_order(account, position, signal) is None


def test_reconcile_state_prefers_broker_truth():
    snapshot = RuntimeState(last_processed_bar="x", last_desired_position="long", broker_has_position=False, broker_has_open_order=False)
    position = PositionSnapshot(symbol="BTC/USD", qty=0.1, market_value=1000, avg_entry_price=90000)
    orders = [OpenOrderSnapshot(order_id="1", client_order_id="cid", side="buy", status="new", qty=None, notional=100)]
    state = reconcile_state(AccountSnapshot(equity=1, cash=1, buying_power=1), position, orders, snapshot)
    assert state.broker_has_position is True
    assert state.broker_has_open_order is True
    assert state.last_submitted_client_order_id == "cid"


def test_latest_closed_bar_time():
    now = datetime(2026, 1, 1, 10, 7, tzinfo=UTC)
    assert latest_closed_bar_time(now) == pd.Timestamp("2026-01-01T10:00:00Z")


class FakeBroker:
    def __init__(self, config, bars, account, position, orders):
        self.config = config
        self._bars = bars
        self._account = account
        self._position = position
        self._orders = orders
        self.buy_calls = []
        self.sell_calls = []

    def get_account_snapshot(self):
        return self._account

    def get_position(self, symbol):
        assert symbol == self.config.symbol
        return self._position

    def list_open_orders(self, symbol):
        assert symbol == self.config.symbol
        return list(self._orders)

    def get_crypto_bars(self, symbol, limit, now=None):
        assert symbol == self.config.symbol
        return self._bars.tail(limit)

    def submit_market_buy_notional(self, symbol, notional, client_order_id):
        self.buy_calls.append((symbol, notional, client_order_id))
        return type("Order", (), {"id": "buy-1"})

    def submit_market_sell_qty(self, symbol, qty, client_order_id):
        self.sell_calls.append((symbol, qty, client_order_id))
        return type("Order", (), {"id": "sell-1"})


def make_bars():
    closes = [100] * 120 + [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 112, 114]
    index = pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [100] * len(closes),
        },
        index=index,
    )


def test_run_once_blocks_when_open_order_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))

    from app import bot as bot_module

    config = bot_module.load_config()
    fake = FakeBroker(
        config,
        make_bars(),
        AccountSnapshot(equity=1000, cash=1000, buying_power=1000),
        None,
        [OpenOrderSnapshot(order_id="1", client_order_id="cid", side="buy", status="new", qty=None, notional=100)],
    )
    monkeypatch.setattr(bot_module, "AlpacaBroker", lambda _config: fake)
    result = run_once(datetime(2026, 1, 2, 9, 1, tzinfo=UTC))
    assert result.action == "blocked_open_order"


def test_run_once_dry_run_buy(monkeypatch, tmp_path):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))

    from app import bot as bot_module

    config = bot_module.load_config()
    fake = FakeBroker(
        config,
        make_bars(),
        AccountSnapshot(equity=1000, cash=1000, buying_power=1000),
        None,
        [],
    )
    monkeypatch.setattr(bot_module, "AlpacaBroker", lambda _config: fake)
    result = run_once(datetime(2026, 1, 2, 9, 1, tzinfo=UTC))
    assert result.action == "dry_run_order"
    assert result.order_client_id is not None


def test_run_once_sell_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))

    from app import bot as bot_module

    bars = make_bars()
    bars.iloc[-1, bars.columns.get_loc("close")] = 70
    config = bot_module.load_config()
    fake = FakeBroker(
        config,
        bars,
        AccountSnapshot(equity=1000, cash=100, buying_power=100),
        PositionSnapshot(symbol="BTC/USD", qty=0.02, market_value=1400, avg_entry_price=90000),
        [],
    )
    monkeypatch.setattr(bot_module, "AlpacaBroker", lambda _config: fake)
    result = run_once(datetime(2026, 1, 2, 0, 1, tzinfo=UTC))
    assert result.action == "submitted_order"
    assert fake.sell_calls
    assert not fake.buy_calls


def test_run_once_same_bar_still_buys_if_flat(monkeypatch, tmp_path):
    monkeypatch.setenv("key", "test")
    monkeypatch.setenv("secret", "test")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))

    from app import bot as bot_module

    state_path = tmp_path / "state.json"
    state_path.write_text(
        """{
  "last_processed_bar": "2026-01-02T08:45:00+00:00",
  "last_desired_position": "long",
  "last_submitted_order_id": null,
  "last_submitted_client_order_id": "btcusd-buy-202601020845",
  "last_stop_level": 99.5,
  "broker_has_position": false,
  "broker_has_open_order": false
}""",
        encoding="utf-8",
    )

    config = bot_module.load_config()
    fake = FakeBroker(
        config,
        make_bars(),
        AccountSnapshot(equity=1000, cash=1000, buying_power=1000),
        None,
        [],
    )
    monkeypatch.setattr(bot_module, "AlpacaBroker", lambda _config: fake)
    result = run_once(datetime(2026, 1, 2, 9, 1, tzinfo=UTC))
    assert result.action == "dry_run_order"
