import sys
from pathlib import Path
from wickhunter.common.logger import setup_logger
from wickhunter.storage.duckdb_catalog import DuckDBAnalyticsSchema

logger = setup_logger("wickhunter.analytics.daily_review")

def run_daily_report(data_dir: str):
    logger.info(f"Generating Daily M4 Review from Parquet lake: {data_dir}")
    
    catalog = DuckDBAnalyticsSchema(Path(data_dir))
    
    try:
        # Aggregation of events
        q = """
        SELECT 
            symbol,
            event_type,
            COUNT(*) as ev_count,
            SUM(qty * price) as total_notional
        FROM execution_data
        WHERE side IN ('BUY', 'SELL')  
        GROUP BY symbol, event_type
        ORDER BY total_notional DESC;
        """
        res = catalog.conn.execute(q).fetchall()
        
        print("\n--- Daily Execution Summary ---")
        for row in res:
            sym, evt, count, notional = row
            # Format notional safely
            notional_str = f"${notional:,.2f}" if notional else "$0.00"
            print(f"- {sym} | {evt}: {count} events ({notional_str})")
            
        # Example PnL proxy if 'net_pnl' column existed (stubbed here)
        # res2 = catalog.conn.execute("SELECT SUM(net_pnl) FROM execution_data WHERE event_type='PULL'").fetchone()
        
    except Exception as e:
        logger.error(f"Failed pulling analytics report: {e}. Check if data lake is populated.")
    finally:
        catalog.close()

if __name__ == "__main__":
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "./data"
    run_daily_report(base_dir)
