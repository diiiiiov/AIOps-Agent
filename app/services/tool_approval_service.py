"""高风险工具审批单与一次性执行令牌。"""

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import config


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ToolApprovalService:
    def __init__(self) -> None:
        self.path = Path(config.task_store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS tool_approvals (
                approval_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, requested_by TEXT NOT NULL,
                tool_name TEXT NOT NULL, args_json TEXT NOT NULL, status TEXT NOT NULL,
                approved_by TEXT, token_hash TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")

    def create(self, *, tenant_id: str, user_id: str, tool_name: str, args: Any) -> str:
        approval_id, now = uuid4().hex, time.time()
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT INTO tool_approvals VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)",
                               (approval_id, tenant_id, user_id, tool_name, _canonical(args), now, now))
        return approval_id

    def approve(self, approval_id: str, *, tenant_id: str, approver: str) -> str | None:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with sqlite3.connect(self.path) as connection:
            result = connection.execute("""UPDATE tool_approvals SET status='approved', approved_by=?,
                token_hash=?, updated_at=? WHERE approval_id=? AND tenant_id=? AND status='pending'""",
                (approver, token_hash, time.time(), approval_id, tenant_id))
        return token if result.rowcount else None

    def consume(self, *, approval_id: str, token: str, tenant_id: str,
                tool_name: str, args: Any) -> bool:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("""SELECT tool_name, args_json, token_hash FROM tool_approvals
                WHERE approval_id=? AND tenant_id=? AND status='approved'""",
                (approval_id, tenant_id)).fetchone()
            if not row or row[0] != tool_name or row[1] != _canonical(args) or not secrets.compare_digest(row[2], token_hash):
                return False
            result = connection.execute("""UPDATE tool_approvals SET status='consumed', token_hash=NULL,
                updated_at=? WHERE approval_id=? AND status='approved'""", (time.time(), approval_id))
        return result.rowcount > 0

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""SELECT approval_id, tenant_id, requested_by, tool_name,
                args_json, status, approved_by, created_at, updated_at FROM tool_approvals
                WHERE tenant_id=? ORDER BY created_at DESC""", (tenant_id,)).fetchall()
        return [dict(row) for row in rows]


def create_tool_approval_service():
    if config.effective_state_store_backend == "postgresql":
        if not config.postgres_dsn:
            raise RuntimeError("PostgreSQL 状态存储需要配置 POSTGRES_DSN")
        from app.services.postgres_tool_approval_service import PostgresToolApprovalService
        return PostgresToolApprovalService(config.postgres_dsn)
    return ToolApprovalService()


tool_approval_service = create_tool_approval_service()
