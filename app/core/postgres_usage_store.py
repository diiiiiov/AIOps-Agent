"""PostgreSQL 模型用量账本。"""

import time
from typing import Any


class PostgresUsageStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 用量账本需要安装 psycopg[binary]") from exc
        self._psycopg, self.dsn = psycopg, dsn
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS model_usage (
                id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, model TEXT NOT NULL,
                input_tokens BIGINT NOT NULL, output_tokens BIGINT NOT NULL,
                estimated_cost DOUBLE PRECISION NOT NULL, created_at DOUBLE PRECISION NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant_time ON model_usage(tenant_id, created_at)")

    def _connect(self):
        return self._psycopg.connect(self.dsn)

    def add(self, tenant_id: str, model: str, input_tokens: int,
            output_tokens: int, estimated_cost: float) -> None:
        with self._connect() as connection:
            connection.execute("""INSERT INTO model_usage
                (tenant_id, model, input_tokens, output_tokens, estimated_cost, created_at)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (tenant_id, model, input_tokens, output_tokens, estimated_cost, time.time()))

    def aggregate(self, since: float) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("""SELECT tenant_id, COUNT(*), SUM(input_tokens),
                SUM(output_tokens), SUM(estimated_cost) FROM model_usage
                WHERE created_at>=%s GROUP BY tenant_id""", (since,)).fetchall()
        return {row[0]: {"requests": row[1], "input_tokens": row[2] or 0,
                         "output_tokens": row[3] or 0, "estimated_cost": row[4] or 0.0}
                for row in rows}
