"""将企业状态从 SQLite 迁移到 PostgreSQL。

默认 dry-run；使用 --apply 才写入。运行前先用 PostgreSQL 配置启动一次应用以创建表。
"""

import argparse
import os
import sqlite3
from pathlib import Path


TABLES = {
    "diagnosis_tasks": ("tasks", {"context_json", "events_json"}),
    "human_handoffs": ("tasks", set()),
    "tool_approvals": ("tasks", {"args_json"}),
    "model_usage": ("usage", set()),
    "agent_memories": ("memory", set()),
}


def sqlite_rows(path: Path, table: str):
    if not path.exists():
        return [], []
    with sqlite3.connect(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return [], []
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
        return [column[1] for column in connection.execute(f'PRAGMA table_info("{table}")')], rows


def migrate(dsn: str, paths: dict[str, Path], apply: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as target:
        for table, (source_key, json_columns) in TABLES.items():
            columns, rows = sqlite_rows(paths[source_key], table)
            if not rows:
                print(f"{table}: 0 rows")
                continue
            target_columns = {
                row[0] for row in target.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,)
                ).fetchall()
            }
            if not target_columns:
                raise RuntimeError(f"目标表 {table} 不存在，请先用 PostgreSQL 配置启动应用创建表")
            selected = [column for column in columns if column in target_columns]
            placeholders = ["%s::jsonb" if column in json_columns else "%s" for column in selected]
            statement = (
                f'INSERT INTO "{table}" ({", ".join(selected)}) '
                f'VALUES ({", ".join(placeholders)}) ON CONFLICT DO NOTHING'
            )
            print(f"{table}: {len(rows)} rows {'will migrate' if apply else '(dry-run)'}")
            if apply:
                for row in rows:
                    target.execute(statement, tuple(row[column] for column in selected))
        if not apply:
            target.rollback()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("POSTGRES_DSN"))
    parser.add_argument("--tasks-db", default="volumes/tasks.db")
    parser.add_argument("--usage-db", default="volumes/usage.db")
    parser.add_argument("--memory-db", default="volumes/memories.db")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("必须通过 --dsn 或 POSTGRES_DSN 提供 PostgreSQL 地址")
    migrate(args.dsn, {
        "tasks": Path(args.tasks_db), "usage": Path(args.usage_db), "memory": Path(args.memory_db)
    }, args.apply)


if __name__ == "__main__":
    main()
