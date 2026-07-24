import hashlib
import json
import secrets
import time
from typing import Any
from uuid import uuid4


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PostgresToolApprovalService:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg, self._dict_row, self.dsn = psycopg, dict_row, dsn
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS tool_approvals (
                approval_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, requested_by TEXT NOT NULL,
                tool_name TEXT NOT NULL, args_json JSONB NOT NULL, status TEXT NOT NULL,
                approved_by TEXT, token_hash TEXT, created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL)""")

    def _connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def create(self, *, tenant_id: str, user_id: str, tool_name: str, args: Any) -> str:
        approval_id, now = uuid4().hex, time.time()
        with self._connect() as connection:
            connection.execute("""INSERT INTO tool_approvals VALUES
                (%s,%s,%s,%s,%s::jsonb,'pending',NULL,NULL,%s,%s)""",
                (approval_id, tenant_id, user_id, tool_name, _canonical(args), now, now))
        return approval_id

    def approve(self, approval_id: str, *, tenant_id: str, approver: str) -> str | None:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            result = connection.execute("""UPDATE tool_approvals SET status='approved', approved_by=%s,
                token_hash=%s, updated_at=%s WHERE approval_id=%s AND tenant_id=%s AND status='pending'""",
                (approver, token_hash, time.time(), approval_id, tenant_id))
        return token if result.rowcount else None

    def consume(self, *, approval_id: str, token: str, tenant_id: str,
                tool_name: str, args: Any) -> bool:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            with connection.transaction():
                row = connection.execute("""SELECT tool_name, args_json::text AS args_json, token_hash
                    FROM tool_approvals WHERE approval_id=%s AND tenant_id=%s AND status='approved'
                    FOR UPDATE""", (approval_id, tenant_id)).fetchone()
                if not row or row["tool_name"] != tool_name or _canonical(json.loads(row["args_json"])) != _canonical(args) \
                        or not secrets.compare_digest(row["token_hash"], token_hash):
                    return False
                result = connection.execute("""UPDATE tool_approvals SET status='consumed', token_hash=NULL,
                    updated_at=%s WHERE approval_id=%s AND status='approved'""", (time.time(), approval_id))
                return result.rowcount > 0

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("""SELECT approval_id, tenant_id, requested_by, tool_name,
                args_json::text AS args_json, status, approved_by, created_at, updated_at
                FROM tool_approvals WHERE tenant_id=%s ORDER BY created_at DESC""", (tenant_id,)).fetchall()
        return list(rows)
