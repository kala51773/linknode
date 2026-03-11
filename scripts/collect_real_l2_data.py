import asyncio
import json
import time
from pathlib import Path

import aiohttp
import websockets

async def fetch_snapshot(symbol: str) -> dict:
    url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol.upper()}&limit=1000"
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()

async def collect_data(symbol: str, duration_sec: int, output_path: str):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    
    events = []
    stream_name_depth = f"{symbol.lower()}@depth@100ms"
    stream_name_trade = f"{symbol.lower()}@trade"
    ws_url = f"wss://fstream.binance.com/stream?streams={stream_name_depth}/{stream_name_trade}"
    
    print(f"Connecting to Binance WS for {duration_sec} seconds to observe real market...")
    end_time = time.time() + duration_sec
    
    snapshot_task = None

    try:
        async for ws in websockets.connect(ws_url):
            try:
                while time.time() < end_time:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(message)
                        stream = data.get("stream", "")
                        payload = data.get("data", {})
                        
                        if stream == stream_name_depth:
                            # Fetch snapshot immediately after first depth update
                            if snapshot_task is None:
                                print(f"First depth message received. Triggering background snapshot fetch...")
                                snapshot_task = asyncio.create_task(fetch_snapshot(symbol))
                                
                            events.append({
                                "event": "depthUpdate",
                                "raw_payload": json.dumps(payload),
                                "symbol": symbol.upper()
                            })
                        elif stream == stream_name_trade:
                            side = "SELL" if payload.get("m") else "BUY"
                            events.append({
                                "event": "trade",
                                "price": payload["p"],
                                "qty": payload["q"],
                                "side": side,
                                "symbol": symbol.upper()
                            })
                            
                        # Check if snapshot task is completed and inject it if so
                        if snapshot_task and snapshot_task.done() and not getattr(snapshot_task, '_injected', False):
                            try:
                                snapshot = snapshot_task.result()
                                events.append({
                                    "event": "snapshot",
                                    "last_update_id": snapshot["lastUpdateId"],
                                    "symbol": symbol.upper(),
                                    "bids": snapshot["bids"],
                                    "asks": snapshot["asks"]
                                })
                                print(f"Snapshot injected into stream. last_update_id: {snapshot['lastUpdateId']}")
                                snapshot_task._injected = True
                            except Exception as e:
                                print(f"Snapshot fetch failed: {e}")
                                snapshot_task._injected = True
                                
                    except asyncio.TimeoutError:
                        continue
                break # Time is up
            except websockets.ConnectionClosed:
                print("WS closed, reconnecting...")
                continue
    except Exception as e:
        print(f"Stopped collecting: {e}")
        
    print(f"Finished collecting. Saving {len(events)} real events to {output_path}...")
    with p.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
            
    print("Done!")

if __name__ == "__main__":
    # Collect 30 seconds of live data by default
    asyncio.run(collect_data("BTCUSDT", 30, "data/real_l2_events.jsonl"))
