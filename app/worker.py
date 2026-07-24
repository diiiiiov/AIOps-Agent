"""独立诊断 Worker 入口。"""

import asyncio

from loguru import logger

from app.services.task_manager import diagnosis_task_manager
from app.services.aiops_service import aiops_service
from app.core.checkpoint_manager import checkpoint_manager


async def main() -> None:
    logger.info("诊断 Worker 已启动")
    checkpointer = await checkpoint_manager.start()
    aiops_service.set_checkpointer(checkpointer)
    try:
        await diagnosis_task_manager.run_worker()
    finally:
        await checkpoint_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
