import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wickhunter.common.config import OKXConfig
from wickhunter.exchange.okx_swap import OKXDepthParser, OKXSwapClient


def _is_success(resp: dict) -> tuple[bool, dict]:
    data = resp.get("data", [])
    row = data[0] if isinstance(data, list) and data else {}
    return resp.get("code") == "0" and row.get("sCode") == "0", row


async def _run(args: argparse.Namespace) -> int:
    cfg = OKXConfig.from_env()
    client = OKXSwapClient(
        depth_parser=OKXDepthParser(),
        api_key=cfg.api_key,
        api_secret=cfg.api_secret,
        api_passphrase=cfg.api_passphrase,
        rest_url=cfg.rest_url,
        ws_public_url=cfg.ws_public_url,
        ws_private_url=cfg.ws_private_url,
        is_demo=cfg.demo,
    )

    print(json.dumps({"demo": cfg.demo, "rest_url": cfg.rest_url}, ensure_ascii=False))

    try:
        account_cfg = await client._signed_request("GET", "/api/v5/account/config")
        details = {}
        cfg_data = account_cfg.get("data", [])
        if isinstance(cfg_data, list) and cfg_data:
            row = cfg_data[0]
            if isinstance(row, dict):
                details = {
                    "acctLv": row.get("acctLv"),
                    "posMode": row.get("posMode"),
                    "perm": row.get("perm"),
                }
        print("account_config", json.dumps(details, ensure_ascii=False))

        open_orders = await client.get_open_orders(args.symbol)
        print(f"open_orders_before={len(open_orders)}")

        client_order_id = f"wh{uuid.uuid4().hex[:12]}"
        place_resp = await client.place_order(
            symbol=args.symbol,
            side=args.side,
            qty=args.qty,
            price=args.price,
            order_type=args.order_type,
            td_mode=args.td_mode,
            pos_side=args.pos_side,
            client_order_id=client_order_id,
        )
        print("place_resp", json.dumps(place_resp, ensure_ascii=False))

        ok, row = _is_success(place_resp)
        if not ok:
            if row.get("sCode") == "51010":
                print("hint=account_mode_mismatch_for_this_order")
            return 2

        if args.no_cancel:
            return 0

        order_id = str(row.get("ordId", ""))
        cancel_resp = await client.cancel_order(symbol=args.symbol, order_id=order_id)
        print("cancel_resp", json.dumps(cancel_resp, ensure_ascii=False))
        return 0
    finally:
        await client.close_session()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test OKX simulated order place/cancel.")
    parser.add_argument("--symbol", default="BTC-USD-SWAP", help="OKX instrument id, e.g. BTC-USD-SWAP")
    parser.add_argument("--side", default="buy", choices=["buy", "sell"], help="Order side")
    parser.add_argument("--qty", default=1.0, type=float, help="Order size")
    parser.add_argument("--price", default=1000.0, type=float, help="Limit price")
    parser.add_argument(
        "--order-type",
        default="limit",
        choices=["limit", "market", "post_only", "fok", "ioc"],
        help="OKX ordType",
    )
    parser.add_argument("--td-mode", default="cross", choices=["cross", "isolated", "cash"], help="Trading mode")
    parser.add_argument("--pos-side", default=None, choices=["long", "short"], help="Position side if needed")
    parser.add_argument("--no-cancel", action="store_true", help="Do not send cancel request after successful place")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
