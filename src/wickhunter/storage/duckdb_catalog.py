import duckdb
from pathlib import Path
from typing import Any, Dict
from wickhunter.common.logger import setup_logger

logger = setup_logger("wickhunter.storage.duckdb")

class DuckDBAnalyticsSchema:
    def __init__(self, data_dir: Path, db_path: str = ":memory:"):
        self.data_dir = data_dir
        self.conn = duckdb.connect(db_path)
        self._mount_views()

    def _mount_views(self) -> None:
        try:
            market_path = self.data_dir / "market" / "**" / "*.parquet"
            exec_path = self.data_dir / "execution" / "**" / "*.parquet"
            
            # Mount views using DuckDB hive partitioning inference.
            # Using TRY/EXCEPT here in case data directories are missing parquet files initially.
            try:
                self.conn.execute(f"CREATE OR REPLACE VIEW market_data AS SELECT * FROM read_parquet('{market_path}', hive_partitioning=1);")
            except duckdb.IOException:
                logger.warning("No parquet files found for market_data yet.")
                
            try:
                self.conn.execute(f"CREATE OR REPLACE VIEW execution_data AS SELECT * FROM read_parquet('{exec_path}', hive_partitioning=1);")
            except duckdb.IOException:
                 logger.warning("No parquet files found for execution_data yet.")
                 
            logger.info("DuckDB views connected over Parquet lake.")
        except Exception as e:
            logger.error(f"Error mounting DuckDB views: {e}")

    def query_fill_ratio(self, symbol: str) -> Dict[str, Any]:
        """Calculates fill ratio metrics for a symbol."""
        try:
            q = f"""
            SELECT 
                COUNT(CASE WHEN event_type='FILL' THEN 1 END) as fills,
                COUNT(CASE WHEN event_type='NEW' THEN 1 END) as new_orders,
                COUNT(CASE WHEN event_type='CANCEL' THEN 1 END) as cancels
            FROM execution_data 
            WHERE symbol='{symbol}'
            """
            res = self.conn.execute(q).fetchone()
            if not res:
                return {"fills": 0, "new_orders": 0, "cancels": 0}
                
            return {
                "fills": res[0] or 0,
                "new_orders": res[1] or 0,
                "cancels": res[2] or 0
            }
        except Exception as e:
            logger.error(f"Error executing analytical query: {e}")
            return {"fills": 0, "new_orders": 0, "cancels": 0}
            
    def close(self) -> None:
        self.conn.close()
