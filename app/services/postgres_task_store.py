"""PostgreSQL 任务存储，面向多实例 API/Worker。"""

import json
import time
from typing import Any


class PostgresTaskStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 模式需要安装 psycopg[binary]") from exc
        self._psycopg = psycopg
        self._dict_row = dict_row
        self.dsn = dsn
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS diagnosis_tasks (
                task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                idempotency_key TEXT, context_json JSONB, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, events_json JSONB NOT NULL DEFAULT '[]',
                error TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON diagnosis_tasks(status)")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency
                ON diagnosis_tasks(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL""")

    def _connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def upsert(self, record: Any) -> None:
        context = record.context.model_dump(exclude_none=True) if record.context else None
        with self._connect() as connection:
            connection.execute("""INSERT INTO diagnosis_tasks
                (task_id, session_id, tenant_id, idempotency_key, context_json, status,
                 attempts, events_json, error, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT(task_id) DO UPDATE SET status=EXCLUDED.status,
                attempts=EXCLUDED.attempts, events_json=EXCLUDED.events_json,
                error=EXCLUDED.error, updated_at=EXCLUDED.updated_at""",
                (record.task_id, record.session_id, record.tenant_id, record.idempotency_key,
                 json.dumps(context), record.status, record.attempts, json.dumps(record.events),
                 record.error, record.created_at, record.updated_at))

    def load_all(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(connection.execute("SELECT * FROM diagnosis_tasks").fetchall())

    def load_one(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM diagnosis_tasks WHERE task_id=%s", (task_id,)).fetchone()

    def recover_interrupted(self, stale_before: float) -> None:
        with self._connect() as connection:
            connection.execute("""UPDATE diagnosis_tasks SET status='failed',
                error='Worker 心跳超时，任务已中断', updated_at=%s
                WHERE status='running' AND updated_at<%s""", (time.time(), stale_before))

    def claim_next(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.transaction():
                row = connection.execute("""SELECT * FROM diagnosis_tasks WHERE status='queued'
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
                if not row:
                    return None
                connection.execute("UPDATE diagnosis_tasks SET status='running', updated_at=%s WHERE task_id=%s",
                                   (time.time(), row["task_id"]))
                row["status"], row["updated_at"] = "running", time.time()
                return row

    def request_cancel(self, task_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute("""UPDATE diagnosis_tasks SET status=CASE
                WHEN status='queued' THEN 'cancelled' ELSE 'cancelling' END, updated_at=%s
                WHERE task_id=%s AND status IN ('queued','running')""", (time.time(), task_id))
            return result.rowcount > 0
