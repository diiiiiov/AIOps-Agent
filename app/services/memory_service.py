"""三层记忆服务：session、tenant、shared。"""

import sqlite3
import time
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import config


class MemoryService:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or config.memory_store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS agent_memories (
                memory_id TEXT PRIMARY KEY, tier TEXT NOT NULL, tenant_id TEXT NOT NULL,
                owner_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON agent_memories(tier, tenant_id)")

    def remember(self, *, tier: str, tenant_id: str, owner_id: str,
                 title: str, content: str, ttl_seconds: int | None = None) -> str:
        if tier not in {"tenant", "shared"}:
            raise ValueError("持久化记忆只支持 tenant 或 shared")
        memory_id = uuid4().hex
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds else None
        scope_tenant = "*" if tier == "shared" else tenant_id
        if tier == "shared":
            content = self._sanitize_shared(content)
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT INTO agent_memories VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (memory_id, tier, scope_tenant, owner_id, title[:200], content[:10000], now, expires_at))
        return memory_id

    @staticmethod
    def _sanitize_shared(content: str) -> str:
        content = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", content)
        content = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[PHONE]", content)
        content = re.sub(
            r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]", content,
        )
        return content

    def recall(self, *, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        now = time.time()
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""SELECT * FROM agent_memories
                WHERE (tenant_id=? OR (tier='shared' AND tenant_id='*'))
                AND (expires_at IS NULL OR expires_at>?)
                ORDER BY created_at DESC LIMIT ?""", (tenant_id, now, min(limit, 100))).fetchall()
        return [dict(row) for row in rows]


def create_memory_service():
    if config.effective_state_store_backend == "postgresql":
        if not config.postgres_dsn:
            raise RuntimeError("PostgreSQL 状态存储需要配置 POSTGRES_DSN")
        from app.services.postgres_memory_service import PostgresMemoryService
        return PostgresMemoryService(config.postgres_dsn)
    return MemoryService()


memory_service = create_memory_service()
