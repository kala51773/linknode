import asyncio
import os
import json
from dotenv import load_dotenv

from wickhunter.common.config import ExchangeConfig
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser


async def main():
    load_dotenv()
    ex_config = ExchangeConfig.from_env()
    
    print(f"Connecting to Binance: testnet={ex_config.testnet}, url={ex_config.rest_url}")

    client = BinanceFuturesClient(
        depth_parser=BinanceFuturesDepthParser(),
        api_key=ex_config.api_key,
        api_secret=ex_config.api_secret,
        rest_url=ex_config.rest_url,
        ws_url=ex_config.ws_url,
    )

    symbol = "BTCUSDT"
    qty = 0.005  # Should be well above minimum notional
    
    try:
        # Check current positions or just place a test order
        print(f"\n[1] Placing MARKET BUY for {qty} {symbol}...")
        buy_resp = await client.place_order(
            symbol=symbol,
            side="BUY",
            qty=qty,
            order_type="MARKET",
        )
        print("Buy response:")
        print(json.dumps(buy_resp, indent=2))
        
        await asyncio.sleep(2.0)
        
        print(f"\n[2] Placing MARKET SELL to close {qty} {symbol}...")
        sell_resp = await client.place_order(
            symbol=symbol,
            side="SELL",
            qty=qty,
            order_type="MARKET",
        )
        print("Sell response:")
        print(json.dumps(sell_resp, indent=2))
        
    except Exception as e:
        print(f"Error occurred: {e}")
        
    finally:
        await client.close_session()

if __name__ == "__main__":
    asyncio.run(main())
