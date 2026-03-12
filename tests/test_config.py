import os
import unittest
from unittest.mock import patch

from wickhunter.common.config import ExchangeConfig, OKXConfig


class TestExchangeConfig(unittest.TestCase):
    def test_from_env_testnet_defaults(self) -> None:
        env = {
            "BINANCE_TESTNET": "true",
            "BINANCE_API_KEY": "k",
            "BINANCE_API_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExchangeConfig.from_env()

        self.assertTrue(cfg.testnet)
        self.assertEqual(cfg.rest_url, "https://demo-fapi.binance.com")
        self.assertEqual(cfg.ws_url, "wss://fstream.binancefuture.com/ws")

    def test_from_env_allows_url_overrides(self) -> None:
        env = {
            "BINANCE_TESTNET": "true",
            "BINANCE_REST_URL": "https://custom-rest",
            "BINANCE_WS_URL": "wss://custom-ws",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExchangeConfig.from_env()

        self.assertEqual(cfg.rest_url, "https://custom-rest")
        self.assertEqual(cfg.ws_url, "wss://custom-ws")


class TestOKXConfig(unittest.TestCase):
    def test_from_env_prod_defaults(self) -> None:
        env = {
            "OKX_DEMO": "false",
            "OKX_API_KEY": "k",
            "OKX_API_SECRET": "s",
            "OKX_API_PASSPHRASE": "p",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = OKXConfig.from_env()

        self.assertFalse(cfg.demo)
        self.assertEqual(cfg.rest_url, "https://www.okx.com")
        self.assertEqual(cfg.ws_public_url, "wss://ws.okx.com:8443/ws/v5/public")
        self.assertEqual(cfg.ws_private_url, "wss://ws.okx.com:8443/ws/v5/private")

    def test_from_env_demo_defaults(self) -> None:
        env = {"OKX_DEMO": "true"}
        with patch.dict(os.environ, env, clear=False):
            cfg = OKXConfig.from_env()

        self.assertTrue(cfg.demo)
        self.assertEqual(cfg.ws_public_url, "wss://wspap.okx.com:8443/ws/v5/public")
        self.assertEqual(cfg.ws_private_url, "wss://wspap.okx.com:8443/ws/v5/private")


if __name__ == "__main__":
    unittest.main()
