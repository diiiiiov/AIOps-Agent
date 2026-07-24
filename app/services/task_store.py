"""诊断任务持久化存储。默认 SQLite，后续可替换为 PostgreSQL。"""

import json
import sqlite3
from pathlib import Path
from typing import Any


class TaskStore:
    def __init__(self, path: str = "volumes/tasks.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS diagnosis_tasks (
                task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, context_json TEXT,
                status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                events_json TEXT NOT NULL DEFAULT '[]', error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON diagnosis_tasks(status)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(diagnosis_tasks)")}
            if "tenant_id" not in columns:
                connection.execute("ALTER TABLE diagnosis_tasks ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public'")
            if "idempotency_key" not in columns:
                connection.execute("ALTER TABLE diagnosis_tasks ADD COLUMN idempotency_key TEXT")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency
                ON diagnosis_tasks(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL""")

    def upsert(self, record: Any) -> None:
        context = record.context.model_dump(exclude_none=True) if record.context else None
        with sqlite3.connect(self.path) as connection:
            connection.execute("""INSERT INTO diagnosis_tasks
                (task_id, session_id, tenant_id, idempotency_key, context_json, status, attempts, events_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET status=excluded.status,
                attempts=excluded.attempts, events_json=excluded.events_json,
                error=excluded.error, updated_at=excluded.updated_at""",
                (record.task_id, record.session_id, record.tenant_id, record.idempotency_key,
                 json.dumps(context, ensure_ascii=False),
                 record.status, record.attempts, json.dumps(record.events, ensure_ascii=False),
                 record.error, record.created_at, record.updated_at))

    def load_all(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("SELECT * FROM diagnosis_tasks").fetchall()]

    def load_one(self, task_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM diagnosis_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def recover_interrupted(self, stale_before: float = float("inf")) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("""UPDATE diagnosis_tasks SET status='failed',
                error='服务重启导致任务中断，请使用新的幂等键重试', updated_at=strftime('%s','now')
                WHERE status='running' AND updated_at<?""", (stale_before,))

    def claim_next(self) -> dict[str, Any] | None:
        """原子领取一个排队任务，防止多个 Worker 重复执行。"""
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""SELECT * FROM diagnosis_tasks
                WHERE status='queued' ORDER BY created_at LIMIT 1""").fetchone()
            if not row:
                connection.commit()
                return None
            result = connection.execute("""UPDATE diagnosis_tasks SET status='running', updated_at=?
                WHERE task_id=? AND status='queued'""", (__import__('time').time(), row["task_id"]))
            connection.commit()
            if not result.rowcount:
                return None
            claimed = dict(row)
            claimed["status"] = "running"
            return claimed

    def request_cancel(self, task_id: str) -> bool:
        now = __import__("time").time()
        with sqlite3.connect(self.path) as connection:
            queued = connection.execute("""UPDATE diagnosis_tasks SET status='cancelled', updated_at=?
                WHERE task_id=? AND status='queued'""", (now, task_id))
            if queued.rowcount:
                return True
            running = connection.execute("""UPDATE diagnosis_tasks SET status='cancelling', updated_at=?
                WHERE task_id=? AND status='running'""", (now, task_id))
        return running.rowcount > 0


def create_task_store():
    from app.config import config
    if config.task_store_backend.lower() == "postgresql":
        if not config.postgres_dsn:
            raise RuntimeError("PostgreSQL 任务存储需要配置 POSTGRES_DSN")
        from app.services.postgres_task_store import PostgresTaskStore
        return PostgresTaskStore(config.postgres_dsn)
    return TaskStore(config.task_store_path)
