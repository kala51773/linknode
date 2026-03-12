import asyncio
import time
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from typing import Any, Dict, List, Optional

from wickhunter.common.logger import setup_logger
from wickhunter.storage.schema import MARKET_DATA_SCHEMA, EXECUTION_EVENT_SCHEMA

logger = setup_logger("wickhunter.storage.parquet")

class ParquetEventBuffer:
    def __init__(self, base_dir: Path, flush_interval_sec: float = 60.0):
        self.base_dir = base_dir
        self.flush_interval_sec = flush_interval_sec
        self.market_buffer: List[Dict[str, Any]] = []
        self.execution_buffer: List[Dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task] = None
        
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "market").mkdir(exist_ok=True)
        (self.base_dir / "execution").mkdir(exist_ok=True)

    def start(self) -> None:
        self._flush_task = asyncio.create_task(self._bg_flush())
        logger.info(f"Parquet writer started. Data dir: {self.base_dir}")

    async def _bg_flush(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.flush_interval_sec)
                self.flush()
        except asyncio.CancelledError:
            pass
        finally:
            self.flush()

    def record_market_data(self, event: Dict[str, Any]) -> None:
        self.market_buffer.append(event)
        
    def record_execution(self, event: Dict[str, Any]) -> None:
        self.execution_buffer.append(event)
        
    def flush(self) -> None:
        now = time.time()
        date_str = time.strftime("%Y-%m-%d", time.gmtime(now))
        # Flush Market Data
        if self.market_buffer:
            batch = self.market_buffer
            self.market_buffer = []
            self._write_to_parquet(batch, MARKET_DATA_SCHEMA, f"market/dt={date_str}", int(now * 1000))
            
        # Flush Execution Data
        if self.execution_buffer:
            batch = self.execution_buffer
            self.execution_buffer = []
            self._write_to_parquet(batch, EXECUTION_EVENT_SCHEMA, f"execution/dt={date_str}", int(now * 1000))

    def _write_to_parquet(self, data: List[Dict[str, Any]], schema: pa.Schema, partition: str, ts: int) -> None:
        try:
            target_dir = self.base_dir / partition
            target_dir.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(data, schema=schema)
            filename = target_dir / f"events_{ts}.parquet"
            pq.write_table(table, filename)
            logger.debug(f"Flushed {len(data)} events to {filename}")
        except Exception as e:
            logger.error(f"Failed to flush parquet: {e}")

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
