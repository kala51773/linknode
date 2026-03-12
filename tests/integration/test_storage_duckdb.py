import pytest
import os
import time
from pathlib import Path
import pyarrow.parquet as pq

from wickhunter.storage.parquet_writer import ParquetEventBuffer
from wickhunter.storage.duckdb_catalog import DuckDBAnalyticsSchema

@pytest.mark.asyncio
async def test_parquet_to_duckdb_pipeline(tmp_path: Path):
    # Setup writer
    data_dir = tmp_path / "data"
    writer = ParquetEventBuffer(base_dir=data_dir, flush_interval_sec=0.1)
    
    # Write some dummy events
    market_ts = int(time.time() * 1000)
    writer.record_market_data({
        "timestamp_ms": market_ts, "symbol": "ETHUSDT", "event_type": "SNAP",
        "bid_px": 3000.0, "bid_qty": 10.0, "ask_px": 3001.0, "ask_qty": 5.0
    })
    writer.record_execution({
        "timestamp_ms": market_ts + 1, "order_id": "O1", "symbol": "ETHUSDT", 
        "side": "BUY", "event_type": "NEW", "price": 3000.0, "qty": 1.0
    })
    writer.record_execution({
        "timestamp_ms": market_ts + 2, "order_id": "O1", "symbol": "ETHUSDT", 
        "side": "BUY", "event_type": "FILL", "price": 3000.0, "qty": 1.0
    })
    
    # Force flush
    writer.flush()
    
    # Init DuckDB
    catalog = DuckDBAnalyticsSchema(data_dir=data_dir)
    res = catalog.query_fill_ratio("ETHUSDT")
    
    # Assert
    assert res["fills"] == 1
    assert res["new_orders"] == 1
    assert res["cancels"] == 0
    
    catalog.close()
