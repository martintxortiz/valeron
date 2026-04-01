from __future__ import annotations

from datetime import datetime, UTC

from alpaca.common.exceptions import APIError

from app.broker import AlpacaBroker
from app.config import load_config


def main() -> None:
    config = load_config()
    broker = AlpacaBroker(config)

    print("Alpaca connectivity check")
    print(f"paper={config.paper}")
    print(f"symbol={config.symbol}")
    print()

    try:
        account = broker.get_account_snapshot()
        print("ACCOUNT: OK")
        print(f"  account_id={account.account_id}")
        print(f"  account_number={account.account_number}")
        print(f"  status={account.status}")
        print(f"  crypto_status={account.crypto_status}")
        print(f"  equity={account.equity}")
        print(f"  cash={account.cash}")
        print(f"  buying_power={account.buying_power}")
    except APIError as exc:
        print("ACCOUNT: FAIL")
        print(str(exc))
        print()
        print("Likely causes:")
        print("- wrong paper API key/secret")
        print("- secret/key regenerated in Alpaca dashboard")
        print("- using live keys against paper endpoint")
        raise SystemExit(1)

    try:
        orders = broker.list_open_orders(config.symbol)
        print()
        print(f"OPEN ORDERS: OK ({len(orders)})")
    except Exception as exc:
        print()
        print("OPEN ORDERS: FAIL")
        print(str(exc))
        raise SystemExit(1)

    try:
        position = broker.get_position(config.symbol)
        print()
        if position is None:
            print("POSITION: OK (flat)")
        else:
            print(f"POSITION: OK qty={position.qty} market_value={position.market_value}")
    except Exception as exc:
        print()
        print("POSITION: FAIL")
        print(str(exc))
        raise SystemExit(1)

    try:
        bars = broker.get_crypto_bars(config.symbol, limit=10, now=datetime.now(UTC))
        print()
        print(f"BARS: OK ({len(bars)} rows)")
        if not bars.empty:
            print(f"  first={bars.index[0]}")
            print(f"  last={bars.index[-1]}")
            print(f"  last_close={bars['close'].iloc[-1]}")
    except Exception as exc:
        print()
        print("BARS: FAIL")
        print(str(exc))
        raise SystemExit(1)

    print()
    print("All checks passed.")


if __name__ == "__main__":
    main()
