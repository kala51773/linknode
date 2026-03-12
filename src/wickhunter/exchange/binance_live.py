import asyncio
import json
import logging
from collections import deque
from typing import Callable, Any

from wickhunter.exchange.binance_futures import BinanceFuturesClient

logger = logging.getLogger("wickhunter.binance_live")

class BinanceUserDataStream:
    """Manages Binance User Data Stream listen key lifecycle and WebSocket connection."""

    def __init__(
        self,
        client: BinanceFuturesClient,
        report_callback: Callable[[dict[str, Any]], None],
        account_callback: Callable[[dict[str, Any]], None] | None = None,
        stream_event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        reconnect_backoff_seconds: float = 1.0,
    ) -> None:
        self.client = client
        self.report_callback = report_callback
        self.account_callback = account_callback
        self.stream_event_callback = stream_event_callback
        self.base_backoff_seconds = max(0.1, reconnect_backoff_seconds)
        self.max_backoff_seconds = 60.0
        self.consecutive_failures = 0
        self._listen_key: str | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._restart_event: asyncio.Event = asyncio.Event()
        self._stop_event: asyncio.Event = asyncio.Event()
        self.listen_key_expired: bool = False
        self.order_report_count: int = 0
        self.account_update_count: int = 0
        self.stream_event_count: int = 0
        self.decode_error_count: int = 0
        self.listen_key_refresh_count: int = 0
        self.listen_key_create_failures: int = 0
        self._seen_order_updates: set[tuple[str, str, str, str, str]] = set()
        self._seen_order_updates_queue: deque[tuple[str, str, str, str, str]] = deque()
        self._max_seen_updates = 20_000

    async def start(self) -> None:
        self._stop_event.clear()
        while not self._stop_event.is_set():
            self._restart_event.clear()
            self.listen_key_expired = False

            logger.info("Creating listen key for user data stream...")
            try:
                self._listen_key = await self.client.create_listen_key()
            except Exception as exc:
                self.listen_key_create_failures += 1
                logger.error(f"Failed to create listen key: {exc}")
                await self._sleep_backoff()
                continue

            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            logger.info(f"Listen key created: {self._listen_key[:5]}...")

            try:
                await self.client.stream_user_data(
                    self._listen_key,
                    self._on_message,
                    stop_event=self._restart_event,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"User data stream disconnected: {exc}")
            finally:
                await self._cancel_keepalive_task()
                await self._delete_listen_key_safe()

            if self._stop_event.is_set():
                break

            self.consecutive_failures = 0 # reset on successful listen key usage
            self.listen_key_refresh_count += 1
            await self._sleep_backoff()

    async def stop(self) -> None:
        self._stop_event.set()
        self._restart_event.set()
        await self._cancel_keepalive_task()
        await self._delete_listen_key_safe()

    async def _keepalive_loop(self) -> None:
        """Ping listen key every 50 minutes to keep it active."""
        try:
            while not self._restart_event.is_set() and not self._stop_event.is_set():
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
            raw_payload = json.loads(message)
            if not isinstance(raw_payload, dict):
                self.decode_error_count += 1
                logger.error("User data stream payload is not a JSON object.")
                return

            payload = raw_payload.get("data") if isinstance(raw_payload.get("data"), dict) else raw_payload
            event_type = payload.get("e")
            if event_type == "ORDER_TRADE_UPDATE":
                order_payload = payload.get("o", {})
                if isinstance(order_payload, dict):
                    update_key = self._build_order_update_key(order_payload)
                    if update_key in self._seen_order_updates:
                        return
                    self._track_seen_order_update(update_key)
                    self.report_callback(order_payload)
                    self.order_report_count += 1
            elif event_type == "ACCOUNT_UPDATE":
                account_payload = payload.get("a", payload)
                if self.account_callback is not None and isinstance(account_payload, dict):
                    self.account_callback(account_payload)
                self.account_update_count += 1
            elif event_type == "listenKeyExpired":
                self.listen_key_expired = True
                logger.warning("Listen key expired in stream, restart required.")
                self._emit_stream_event("listen_key_expired", payload)
                self._restart_event.set()
        except Exception as e:
            self.decode_error_count += 1
            logger.error(f"Failed to process user data stream message: {e}")

    def _emit_stream_event(self, event_type: str, payload: dict[str, Any]) -> None:
        callback = self.stream_event_callback
        if callback is None:
            return
        callback(event_type, payload)
        self.stream_event_count += 1

    async def _cancel_keepalive_task(self) -> None:
        if self._keepalive_task is None:
            return
        self._keepalive_task.cancel()
        try:
            await self._keepalive_task
        except asyncio.CancelledError:
            pass
        finally:
            self._keepalive_task = None

    async def _delete_listen_key_safe(self) -> None:
        if not self._listen_key:
            return
        try:
            await self.client.delete_listen_key()
            logger.info("Listen key deleted.")
        except Exception as e:
            logger.error(f"Error deleting listen key: {e}")
        finally:
            self._listen_key = None

    async def _sleep_backoff(self) -> None:
        self.consecutive_failures += 1
        sleep_duration = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** (self.consecutive_failures - 1)))
        logger.warning(f"Reconnecting after {sleep_duration:.1f}s backoff (failure {self.consecutive_failures})...")
        await asyncio.sleep(sleep_duration)

    def _build_order_update_key(self, order_payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
        client_id = str(order_payload.get("c", ""))
        order_id = str(order_payload.get("i", ""))
        status = str(order_payload.get("X", ""))
        filled_qty = str(order_payload.get("z", ""))
        trade_time = str(order_payload.get("T", order_payload.get("t", "")))
        return (client_id, order_id, status, filled_qty, trade_time)

    def _track_seen_order_update(self, key: tuple[str, str, str, str, str]) -> None:
        self._seen_order_updates.add(key)
        self._seen_order_updates_queue.append(key)
        if len(self._seen_order_updates_queue) <= self._max_seen_updates:
            return
        old = self._seen_order_updates_queue.popleft()
        self._seen_order_updates.discard(old)
