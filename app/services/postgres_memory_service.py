"""PostgreSQL 企业记忆存储。"""

import re
import time
from typing import Any
from uuid import uuid4


class PostgresMemoryService:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg, self._dict_row, self.dsn = psycopg, dict_row, dsn
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS agent_memories (
                memory_id TEXT PRIMARY KEY, tier TEXT NOT NULL, tenant_id TEXT NOT NULL,
                owner_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL, expires_at DOUBLE PRECISION)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON agent_memories(tier, tenant_id)")

    def _connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def remember(self, *, tier: str, tenant_id: str, owner_id: str,
                 title: str, content: str, ttl_seconds: int | None = None) -> str:
        if tier not in {"tenant", "shared"}:
            raise ValueError("持久化记忆只支持 tenant 或 shared")
        if tier == "shared":
            content = self._sanitize_shared(content)
        memory_id, now = uuid4().hex, time.time()
        with self._connect() as connection:
            connection.execute("""INSERT INTO agent_memories VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (memory_id, tier, "*" if tier == "shared" else tenant_id, owner_id,
                 title[:200], content[:10000], now, now + ttl_seconds if ttl_seconds else None))
        return memory_id

    def recall(self, *, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("""SELECT * FROM agent_memories
                WHERE (tenant_id=%s OR (tier='shared' AND tenant_id='*'))
                AND (expires_at IS NULL OR expires_at>%s)
                ORDER BY created_at DESC LIMIT %s""", (tenant_id, time.time(), min(limit, 100))).fetchall()
        return list(rows)

    @staticmethod
    def _sanitize_shared(content: str) -> str:
        content = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", content)
        content = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[PHONE]", content)
        return re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+",
                      r"\1=[REDACTED]", content)
