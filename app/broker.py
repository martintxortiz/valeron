from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.common.enums import Sort
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from app.config import Config


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float


@dataclass(frozen=True)
class OpenOrderSnapshot:
    order_id: str
    client_order_id: str
    side: str
    status: str
    qty: float | None
    notional: float | None


class AlpacaBroker:
    def __init__(self, config: Config):
        self.config = config
        self.trading = TradingClient(config.api_key, config.api_secret, paper=config.paper)
        self.data = CryptoHistoricalDataClient(config.api_key, config.api_secret)

    def get_account_snapshot(self) -> AccountSnapshot:
        account = self.trading.get_account()
        cash = float(getattr(account, "cash", 0) or 0)
        buying_power = float(getattr(account, "non_marginable_buying_power", 0) or getattr(account, "buying_power", 0) or 0)
        equity = float(getattr(account, "equity", 0) or 0)
        return AccountSnapshot(equity=equity, cash=cash, buying_power=buying_power)

    def get_position(self, symbol: str) -> PositionSnapshot | None:
        try:
            position = self.trading.get_open_position(symbol)
        except APIError as exc:
            if "position does not exist" in str(exc).lower() or getattr(exc, "status_code", None) == 404:
                return None
            raise
        return PositionSnapshot(
            symbol=str(position.symbol),
            qty=float(position.qty),
            market_value=float(position.market_value),
            avg_entry_price=float(position.avg_entry_price),
        )

    def list_open_orders(self, symbol: str) -> list[OpenOrderSnapshot]:
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol], nested=False)
        orders = self.trading.get_orders(filter=request)
        out = []
        for order in orders:
            out.append(
                OpenOrderSnapshot(
                    order_id=str(order.id),
                    client_order_id=str(order.client_order_id),
                    side=str(order.side.value if hasattr(order.side, "value") else order.side),
                    status=str(order.status.value if hasattr(order.status, "value") else order.status),
                    qty=float(order.qty) if order.qty is not None else None,
                    notional=float(order.notional) if order.notional is not None else None,
                )
            )
        return out

    def get_crypto_bars(self, symbol: str, limit: int, now: datetime | None = None) -> pd.DataFrame:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=45)
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=now,
            limit=limit,
            sort=Sort.DESC,
        )
        bars = self.data.get_crypto_bars(request).df
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level=0)
        bars = bars.rename(columns=str.lower).sort_index()
        return bars[["open", "high", "low", "close", "volume"]].tail(limit)

    def submit_market_buy_notional(self, symbol: str, notional: float, client_order_id: str):
        request = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            type="market",
            client_order_id=client_order_id,
        )
        return self.trading.submit_order(order_data=request)

    def submit_market_sell_qty(self, symbol: str, qty: float, client_order_id: str):
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            type="market",
            client_order_id=client_order_id,
        )
        return self.trading.submit_order(order_data=request)
