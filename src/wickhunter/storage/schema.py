import pyarrow as pa

# Examples based on PRD
MARKET_DATA_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("symbol", pa.string()),
    ("event_type", pa.string()),
    ("bid_px", pa.float64()),
    ("bid_qty", pa.float64()),
    ("ask_px", pa.float64()),
    ("ask_qty", pa.float64()),
])

EXECUTION_EVENT_SCHEMA = pa.schema([
    ("timestamp_ms", pa.int64()),
    ("order_id", pa.string()),
    ("symbol", pa.string()),
    ("side", pa.string()),
    ("event_type", pa.string()), # NEW, FILL, CANCEL
    ("price", pa.float64()),
    ("qty", pa.float64()),
])
