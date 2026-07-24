import time
from typing import Any
from uuid import uuid4


class PostgresHandoffService:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg, self._dict_row, self.dsn = psycopg, dict_row, dsn
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS human_handoffs (
                handoff_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                requested_by TEXT NOT NULL, assigned_to TEXT, reason TEXT NOT NULL,
                status TEXT NOT NULL, resolution TEXT, created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL)""")

    def _connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def create(self, *, task_id: str, tenant_id: str, user_id: str, reason: str) -> dict[str, Any]:
        now = time.time()
        record = {"handoff_id": uuid4().hex, "task_id": task_id, "tenant_id": tenant_id,
                  "requested_by": user_id, "assigned_to": None, "reason": reason,
                  "status": "pending", "resolution": None, "created_at": now, "updated_at": now}
        with self._connect() as connection:
            connection.execute("INSERT INTO human_handoffs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                               tuple(record.values()))
        return record

    def update(self, handoff_id: str, *, tenant_id: str, status: str, assigned_to: str,
               resolution: str | None = None) -> bool:
        with self._connect() as connection:
            result = connection.execute("""UPDATE human_handoffs SET status=%s, assigned_to=%s,
                resolution=%s, updated_at=%s WHERE handoff_id=%s AND tenant_id=%s""",
                (status, assigned_to, resolution, time.time(), handoff_id, tenant_id))
        return result.rowcount > 0

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(connection.execute("""SELECT * FROM human_handoffs WHERE tenant_id=%s
                ORDER BY created_at DESC""", (tenant_id,)).fetchall())
