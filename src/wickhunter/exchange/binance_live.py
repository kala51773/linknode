import asyncio
import json
import logging
from typing import Callable, Any

from wickhunter.exchange.binance_futures import BinanceFuturesClient

logger = logging.getLogger("wickhunter.binance_live")

class BinanceUserDataStream:
    """Manages Binance User Data Stream listen key lifecycle and WebSocket connection."""

    def __init__(self, client: BinanceFuturesClient, report_callback: Callable[[dict[str, Any]], None]) -> None:
        self.client = client
        self.report_callback = report_callback
        self._listen_key: str | None = None
        self._keepalive_task: asyncio.Task | None = None

    async def start(self) -> None:
        logger.info("Creating limit key for user data stream...")
        self._listen_key = await self.client.create_listen_key()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        logger.info(f"Listen key created: {self._listen_key[:5]}...")
        
        # This will block and run the WS loop. 
        # Typically called via asyncio.create_task() by the caller.
        await self.client.stream_user_data(self._listen_key, self._on_message)

    async def stop(self) -> None:
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._listen_key:
            try:
                await self.client.delete_listen_key()
                logger.info("Listen key deleted.")
            except Exception as e:
                logger.error(f"Error deleting listen key: {e}")

    async def _keepalive_loop(self) -> None:
        """Ping listen key every 50 minutes to keep it active."""
        try:
            while True:
                await asyncio.sleep(50 * 60)
                if self._listen_key:
                    await self.client.keepalive_listen_key()
                    logger.debug("Listen key keepalive ping successful.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Keepalive loop exception: {e}")

    def _on_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
            event_type = payload.get("e")
            if event_type == "ORDER_TRADE_UPDATE":
                order_payload = payload.get("o", {})
                self.report_callback(order_payload)
            elif event_type == "ACCOUNT_UPDATE":
                pass # Later we can handle balance changes
            elif event_type == "listenKeyExpired":
                logger.warning("Listen key expired in stream, restart required.")
                # Could trigger re-connect logic
        except Exception as e:
            logger.error(f"Failed to process user data stream message: {e}")
