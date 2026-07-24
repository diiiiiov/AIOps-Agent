"""人工接管记录与状态管理。"""

import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import config


class HandoffService:
    def __init__(self) -> None:
        self.path = Path(config.task_store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS human_handoffs (
                handoff_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                requested_by TEXT NOT NULL, assigned_to TEXT, reason TEXT NOT NULL,
                status TEXT NOT NULL, resolution TEXT, created_at REAL NOT NULL,
                updated_at REAL NOT NULL)""")

    def create(self, *, task_id: str, tenant_id: str, user_id: str, reason: str) -> dict[str, Any]:
        now = time.time()
        record = {
            "handoff_id": uuid4().hex, "task_id": task_id, "tenant_id": tenant_id,
            "requested_by": user_id, "assigned_to": None, "reason": reason,
            "status": "pending", "resolution": None, "created_at": now, "updated_at": now,
        }
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT INTO human_handoffs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(record.values()))
        return record

    def update(self, handoff_id: str, *, tenant_id: str, status: str, assigned_to: str,
               resolution: str | None = None) -> bool:
        with sqlite3.connect(self.path) as connection:
            result = connection.execute("""UPDATE human_handoffs SET status=?, assigned_to=?,
                resolution=?, updated_at=? WHERE handoff_id=? AND tenant_id=?""",
                (status, assigned_to, resolution, time.time(), handoff_id, tenant_id))
        return result.rowcount > 0

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM human_handoffs WHERE tenant_id=? ORDER BY created_at DESC",
                                      (tenant_id,)).fetchall()
        return [dict(row) for row in rows]


def create_handoff_service():
    if config.effective_state_store_backend == "postgresql":
        if not config.postgres_dsn:
            raise RuntimeError("PostgreSQL 状态存储需要配置 POSTGRES_DSN")
        from app.services.postgres_handoff_service import PostgresHandoffService
        return PostgresHandoffService(config.postgres_dsn)
    return HandoffService()


handoff_service = create_handoff_service()
