"""模型用量持久化账本。"""

import sqlite3
import time
from pathlib import Path
from typing import Any

from app.config import config


class UsageStore:
    def __init__(self) -> None:
        self.path = Path(config.usage_store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS model_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL, estimated_cost REAL NOT NULL,
                created_at REAL NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant_time ON model_usage(tenant_id, created_at)")

    def add(self, tenant_id: str, model: str, input_tokens: int,
            output_tokens: int, estimated_cost: float) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT INTO model_usage VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                               (tenant_id, model, input_tokens, output_tokens, estimated_cost, time.time()))

    def aggregate(self, since: float) -> dict[str, dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("""SELECT tenant_id, COUNT(*), SUM(input_tokens),
                SUM(output_tokens), SUM(estimated_cost) FROM model_usage
                WHERE created_at>=? GROUP BY tenant_id""", (since,)).fetchall()
        return {row[0]: {"requests": row[1], "input_tokens": row[2] or 0,
                         "output_tokens": row[3] or 0, "estimated_cost": row[4] or 0.0}
                for row in rows}


def create_usage_store():
    if config.effective_state_store_backend == "postgresql":
        if not config.postgres_dsn:
            raise RuntimeError("PostgreSQL 状态存储需要配置 POSTGRES_DSN")
        from app.core.postgres_usage_store import PostgresUsageStore
        return PostgresUsageStore(config.postgres_dsn)
    return UsageStore()


usage_store = create_usage_store()
