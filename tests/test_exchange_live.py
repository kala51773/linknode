import asyncio
import unittest

from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.binance_live import BinanceUserDataStream


class TestBinanceUserDataStream(unittest.TestCase):
    def _build_stream(self) -> tuple[BinanceUserDataStream, list[dict[str, object]], list[dict[str, object]], list[tuple[str, dict[str, object]]]]:
        order_reports: list[dict[str, object]] = []
        account_updates: list[dict[str, object]] = []
        stream_events: list[tuple[str, dict[str, object]]] = []

        client = BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser())
        stream = BinanceUserDataStream(
            client=client,
            report_callback=lambda payload: order_reports.append(payload),
            account_callback=lambda payload: account_updates.append(payload),
            stream_event_callback=lambda et, payload: stream_events.append((et, payload)),
        )
        return stream, order_reports, account_updates, stream_events

    def test_order_trade_update_routes_to_report_callback(self) -> None:
        stream, order_reports, account_updates, stream_events = self._build_stream()
        stream._on_message(
            '{"e":"ORDER_TRADE_UPDATE","o":{"c":"wh_1","i":123,"X":"NEW","z":"0"}}'
        )

        self.assertEqual(len(order_reports), 1)
        self.assertEqual(order_reports[0]["c"], "wh_1")
        self.assertEqual(stream.order_report_count, 1)
        self.assertEqual(stream.account_update_count, 0)
        self.assertEqual(len(account_updates), 0)
        self.assertEqual(len(stream_events), 0)

    def test_account_update_routes_to_account_callback(self) -> None:
        stream, order_reports, account_updates, _ = self._build_stream()
        stream._on_message(
            '{"e":"ACCOUNT_UPDATE","a":{"m":"ORDER","B":[{"a":"USDT","wb":"100.0"}]}}'
        )

        self.assertEqual(stream.account_update_count, 1)
        self.assertEqual(len(account_updates), 1)
        self.assertEqual(account_updates[0]["m"], "ORDER")
        self.assertEqual(stream.order_report_count, 0)
        self.assertEqual(len(order_reports), 0)

    def test_listen_key_expired_sets_flag_and_emits_event(self) -> None:
        stream, _, _, stream_events = self._build_stream()
        stream._on_message('{"e":"listenKeyExpired"}')

        self.assertTrue(stream.listen_key_expired)
        self.assertEqual(stream.stream_event_count, 1)
        self.assertEqual(len(stream_events), 1)
        self.assertEqual(stream_events[0][0], "listen_key_expired")

    def test_combined_stream_payload_is_supported(self) -> None:
        stream, order_reports, _, _ = self._build_stream()
        stream._on_message(
            '{"stream":"x","data":{"e":"ORDER_TRADE_UPDATE","o":{"c":"wh_2","X":"FILLED","z":"1"}}}'
        )

        self.assertEqual(len(order_reports), 1)
        self.assertEqual(order_reports[0]["c"], "wh_2")
        self.assertEqual(stream.order_report_count, 1)

    def test_malformed_json_increments_decode_error_counter(self) -> None:
        stream, _, _, _ = self._build_stream()
        stream._on_message("{broken")

        self.assertEqual(stream.decode_error_count, 1)

    def test_duplicate_order_updates_are_deduplicated(self) -> None:
        stream, order_reports, _, _ = self._build_stream()
        payload = '{"e":"ORDER_TRADE_UPDATE","o":{"c":"wh_1","i":123,"X":"NEW","z":"0","T":1}}'
        stream._on_message(payload)
        stream._on_message(payload)

        self.assertEqual(len(order_reports), 1)
        self.assertEqual(stream.order_report_count, 1)


class FakeUserDataClient:
    def __init__(self) -> None:
        self.create_calls = 0
        self.delete_calls = 0
        self.stream_calls: list[str] = []

    async def create_listen_key(self) -> str:
        self.create_calls += 1
        return f"lk_{self.create_calls}"

    async def keepalive_listen_key(self) -> None:
        return None

    async def delete_listen_key(self) -> None:
        self.delete_calls += 1

    async def stream_user_data(self, listen_key: str, callback, stop_event: asyncio.Event | None = None) -> None:
        self.stream_calls.append(listen_key)
        if len(self.stream_calls) == 1:
            callback('{"e":"listenKeyExpired"}')
            if stop_event is not None and stop_event.is_set():
                return

        while stop_event is not None and not stop_event.is_set():
            await asyncio.sleep(0.001)


class TestBinanceUserDataStreamAsync(unittest.IsolatedAsyncioTestCase):
    async def test_start_recreates_listen_key_after_expired_event(self) -> None:
        client = FakeUserDataClient()
        stream = BinanceUserDataStream(
            client=client,  # type: ignore[arg-type]
            report_callback=lambda _: None,
            reconnect_backoff_seconds=0.0,
        )

        task = asyncio.create_task(stream.start())
        for _ in range(200):
            if client.create_calls >= 2:
                break
            await asyncio.sleep(0.001)

        await stream.stop()
        await asyncio.wait_for(task, timeout=1.0)

        self.assertGreaterEqual(client.create_calls, 2)
        self.assertGreaterEqual(stream.listen_key_refresh_count, 1)
        self.assertGreaterEqual(client.delete_calls, 1)

    async def test_reconnect_does_not_duplicate_same_order_report(self) -> None:
        class ReplayClient(FakeUserDataClient):
            async def stream_user_data(self, listen_key: str, callback, stop_event: asyncio.Event | None = None) -> None:
                self.stream_calls.append(listen_key)
                callback('{"e":"ORDER_TRADE_UPDATE","o":{"c":"wh_9","i":9,"X":"NEW","z":"0","T":100}}')
                if len(self.stream_calls) == 1:
                    callback('{"e":"listenKeyExpired"}')
                    if stop_event is not None and stop_event.is_set():
                        return
                while stop_event is not None and not stop_event.is_set():
                    await asyncio.sleep(0.001)

        client = ReplayClient()
        seen: list[dict[str, object]] = []
        stream = BinanceUserDataStream(
            client=client,  # type: ignore[arg-type]
            report_callback=lambda p: seen.append(p),
            reconnect_backoff_seconds=0.0,
        )

        task = asyncio.create_task(stream.start())
        for _ in range(300):
            if client.create_calls >= 2:
                break
            await asyncio.sleep(0.001)
        await stream.stop()
        await asyncio.wait_for(task, timeout=1.0)

        self.assertGreaterEqual(client.create_calls, 2)
        self.assertEqual(len(seen), 1)
        self.assertEqual(stream.order_report_count, 1)


if __name__ == "__main__":
    unittest.main()
