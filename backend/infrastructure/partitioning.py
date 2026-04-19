"""PostgreSQL Partitioning Lifecycle Manager.

Handles the automatic generation of rolling time-window partitions for declarative 
table sets mapped in our operational data store (`docs/02-services/data.md`).
"""

from __future__ import annotations

import structlog
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text

logger = structlog.get_logger(__name__)

# The canonical tables requiring monthly partitioning schemas.
PARTITIONED_TABLES = [
    "audit_events",
    "outbox_events",
    "task_transitions",
]

class PartitionManager:
    """Manages creation and expiration of Postgres table partitions."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def ensure_partitions_out_to(self, months_ahead: int = 2):
        """
        Idempotently generates monthly partitions starting from the current month
        out to `months_ahead`. This should run on Startup or via Cron.
        """
        today = date.today()
        # Always start from current month start
        current_iter = date(today.year, today.month, 1)

        async with self.engine.begin() as conn:
            for _ in range(months_ahead + 1):
                next_month = current_iter + relativedelta(months=1)
                
                start_str = current_iter.strftime('%Y-%m-%d')
                end_str = next_month.strftime('%Y-%m-%d')
                partition_suffix = current_iter.strftime('%Y_%m')
                
                for table in PARTITIONED_TABLES:
                    partition_name = f"{table}_{partition_suffix}"
                    
                    stmt = f"""
                    CREATE TABLE IF NOT EXISTS {partition_name} 
                    PARTITION OF {table} 
                    FOR VALUES FROM ('{start_str}') TO ('{end_str}');
                    """
                    
                    try:
                        await conn.execute(text(stmt))
                        logger.debug("partition_ensured", table=partition_name, bounds=f"{start_str} to {end_str}")
                    except Exception as e:
                        # Depending on postgres setups, it might complain if parent doesn't exist yet (during early migrations)
                        logger.warning("partition_create_failed", table=partition_name, error=str(e))
                
                # Advance iterator
                current_iter = next_month

    async def drop_old_partitions(self, retention_days: dict[str, int]):
        """
        Examines tables and brutally drops old partitions exceeding retention limits.
        In an enterprise scenario, an archive routine would export this to cold-storage (S3/GCS) first.
        """
        today = date.today()
        
        async with self.engine.begin() as conn:
            for table, days in retention_days.items():
                cutoff = today - timedelta(days=days)
                cutoff_suffix = cutoff.strftime('%Y_%m')
                target_drop_name = f"{table}_{cutoff_suffix}"
                
                # Drops the partition and completely deletes the underlying data.
                drop_stmt = f"DROP TABLE IF EXISTS {target_drop_name};"
                try:
                    await conn.execute(text(drop_stmt))
                    logger.info("partition_dropped", table=target_drop_name, retention=days)
                except Exception as e:
                    logger.error("partition_drop_failed", table=target_drop_name, error=str(e))
