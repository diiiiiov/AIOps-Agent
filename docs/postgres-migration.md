# PostgreSQL 状态迁移

1. 备份 `volumes/tasks.db`、`volumes/usage.db` 和 `volumes/memories.db`。
2. 配置 PostgreSQL 后启动一次应用，创建目标表。
3. 执行预览：

```powershell
python scripts/migrate_sqlite_to_postgres.py --dsn "postgresql://user:password@host:5432/superbiz"
```

4. 确认各表行数后正式迁移：

```powershell
python scripts/migrate_sqlite_to_postgres.py --dsn "postgresql://user:password@host:5432/superbiz" --apply
```

脚本使用 `ON CONFLICT DO NOTHING`，可以安全重跑。迁移完成并核对数据后，再设置：

```env
TASK_STORE_BACKEND=postgresql
STATE_STORE_BACKEND=postgresql
INLINE_TASK_EXECUTION=false
```
