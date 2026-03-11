import json
from pathlib import Path

def generate_l2_data(output_path: str):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    
    events = []
    
    # 1. Initial Snapshot
    events.append({
        "event": "snapshot",
        "last_update_id": 100,
        "symbol": "BTCUSDT",
        "bids": [["99.5", "10.0"], ["100.0", "5.0"]],
        "asks": [["100.5", "5.0"], ["101.0", "10.0"]]
    })
    
    # 2. Depth Update (spread thickens)
    raw_depth = '{"e":"depthUpdate","E":1700,"s":"BTCUSDT","U":101,"u":102,"b":[["100.0","3.0"]],"a":[["100.2","2.0"]]}'
    events.append({
        "event": "depthUpdate",
        "raw_payload": raw_depth
    })
    
    # 3. Market Drop (trade event hitting the bids)
    events.append({
        "event": "trade",
        "price": "99.9",
        "qty": "2.0",
        "side": "SELL",
        "symbol": "BTCUSDT",
    })
    
    # 4. Another trade dropping the price lower towards our Level 2 limit
    events.append({
        "event": "trade",
        "price": "99.0",
        "qty": "5.0",
        "side": "SELL",
        "symbol": "BTCUSDT",
    })
    
    with p.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

if __name__ == "__main__":
    generate_l2_data("data/sample_l2_events.jsonl")
    print("Generated data/sample_l2_events.jsonl")
