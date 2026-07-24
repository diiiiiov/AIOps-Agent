"""LangGraph Checkpointer 生命周期管理。"""

from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from app.config import config


class CheckpointManager:
    def __init__(self) -> None:
        self.checkpointer: Any = MemorySaver()
        self._context_manager = None

    async def start(self) -> Any:
        if config.checkpoint_backend.lower() != "postgresql":
            return self.checkpointer
        dsn = config.checkpoint_postgres_dsn or config.postgres_dsn
        if not dsn:
            raise RuntimeError("PostgreSQL Checkpointer 需要 CHECKPOINT_POSTGRES_DSN 或 POSTGRES_DSN")
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:
            raise RuntimeError("需要安装 langgraph-checkpoint-postgres") from exc
        self._context_manager = AsyncPostgresSaver.from_conn_string(dsn)
        self.checkpointer = await self._context_manager.__aenter__()
        await self.checkpointer.setup()
        return self.checkpointer

    async def stop(self) -> None:
        if self._context_manager:
            await self._context_manager.__aexit__(None, None, None)
            self._context_manager = None


checkpoint_manager = CheckpointManager()
