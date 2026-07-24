"""异步诊断任务管理。

当前使用进程内存储，接口设计与 Redis/Celery 兼容：后续只需替换存储和调度实现。
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.config import config
from app.models.aiops import DiagnosisContext
from app.services.aiops_service import aiops_service
from app.services.task_store import create_task_store
from app.core.metrics import metrics
from app.core.usage_tracker import usage_tracker
from app.core.request_context import (
    RequestContext, get_request_context, reset_request_context, set_request_context,
)


@dataclass
class TaskRecord:
    task_id: str
    session_id: str
    tenant_id: str
    context: DiagnosisContext | None
    idempotency_key: str | None = None
    status: str = "queued"
    attempts: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class DiagnosisTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._store = create_task_store()
        self._store.recover_interrupted(time.time() - config.task_stale_seconds)
        for row in self._store.load_all():
            record = self._record_from_row(row)
            self._tasks[record.task_id] = record
            if record.idempotency_key:
                self._idempotency[(record.tenant_id, record.idempotency_key)] = record.task_id

    async def submit(
        self,
        session_id: str,
        context: DiagnosisContext | None,
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        async with self._lock:
            tenant_id = get_request_context().tenant_id
            if usage_tracker.budget_exceeded():
                raise RuntimeError("当前租户已达到模型预算上限")
            idempotency_scope = (tenant_id, idempotency_key) if idempotency_key else None
            if idempotency_scope and idempotency_scope in self._idempotency:
                return self._tasks[self._idempotency[idempotency_scope]]
            active = sum(item.status in {"queued", "running"} for item in self._tasks.values())
            if active >= config.max_concurrent_tasks:
                raise RuntimeError("诊断任务达到并发上限，请稍后重试")
            record = TaskRecord(
                task_id=uuid4().hex, session_id=session_id, tenant_id=tenant_id,
                context=context, idempotency_key=idempotency_key,
            )
            metrics.increment("diagnosis_tasks_submitted_total")
            self._tasks[record.task_id] = record
            self._store.upsert(record)
            if idempotency_key:
                self._idempotency[(tenant_id, idempotency_key)] = record.task_id
            if config.inline_task_execution:
                self._running[record.task_id] = asyncio.create_task(self._run(record))
            return record

    @staticmethod
    def _record_from_row(row: dict[str, Any]) -> TaskRecord:
        raw_context = row.get("context_json")
        context_data = json.loads(raw_context) if isinstance(raw_context, str) else raw_context
        raw_events = row.get("events_json") or []
        events = json.loads(raw_events) if isinstance(raw_events, str) else list(raw_events)
        return TaskRecord(
            task_id=row["task_id"], session_id=row["session_id"], tenant_id=row["tenant_id"],
            context=DiagnosisContext.model_validate(context_data) if context_data else None,
            idempotency_key=row.get("idempotency_key"), status=row["status"], attempts=row["attempts"],
            events=events, error=row["error"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def run_worker(self) -> None:
        """持续领取并执行任务；用于独立 Worker 进程。"""
        while True:
            row = self._store.claim_next()
            if not row:
                await asyncio.sleep(config.worker_poll_interval_seconds)
                continue
            record = self._record_from_row(row)
            self._tasks[record.task_id] = record
            current = asyncio.current_task()
            if current:
                self._running[record.task_id] = current
            await self._run(record)

    async def _run(self, record: TaskRecord) -> None:
        token = set_request_context(RequestContext(
            request_id=f"task-{record.task_id}", tenant_id=record.tenant_id,
            user_id="diagnosis-worker", roles=("operator",),
        ))
        try:
            await self._run_scoped(record)
        finally:
            reset_request_context(token)

    async def _run_scoped(self, record: TaskRecord) -> None:
        record.status = "running"
        metrics.increment("diagnosis_tasks_running_total")
        self._store.upsert(record)
        for attempt in range(1, 4):
            record.attempts = attempt
            if attempt > 1:
                metrics.increment("diagnosis_task_retries_total")
            self._store.upsert(record)
            try:
                await asyncio.wait_for(
                    self._run_attempt(record), timeout=config.diagnosis_timeout_seconds
                )
                record.status = "completed"
                record.error = None
                record.updated_at = time.time()
                metrics.increment("diagnosis_tasks_completed_total")
                self._store.upsert(record)
                return
            except asyncio.CancelledError:
                record.status = "cancelled"
                self._store.upsert(record)
                raise
            except asyncio.TimeoutError:
                record.error = f"诊断超过总时限 {config.diagnosis_timeout_seconds} 秒"
                if attempt < 3:
                    await asyncio.sleep(2 ** (attempt - 1))
            except Exception as exc:
                record.error = str(exc)
                if attempt < 3:
                    await asyncio.sleep(2 ** (attempt - 1))
        record.status = "failed"
        metrics.increment("diagnosis_tasks_failed_total")
        self._store.upsert(record)

    async def _run_attempt(self, record: TaskRecord) -> None:
        async for event in aiops_service.diagnose(record.session_id, record.context):
            persisted = self._store.load_one(record.task_id)
            if persisted and persisted["status"] == "cancelling":
                raise asyncio.CancelledError
            is_terminal = event.get("type") in {"complete", "report", "error"}
            if len(record.events) >= config.max_task_events:
                if is_terminal:
                    record.events[-1] = event
                    record.updated_at = time.time()
                    self._store.upsert(record)
                    if event.get("type") == "error":
                        raise RuntimeError(event.get("message", "诊断失败"))
                    continue
                if not record.events or record.events[-1].get("type") != "event_limit":
                    record.events.append({
                        "type": "event_limit",
                        "message": f"事件数量超过 {config.max_task_events}，后续中间事件不再保存",
                    })
                continue
            serialized = json.dumps(event, ensure_ascii=False, default=str).encode("utf-8")
            if len(serialized) > config.max_task_event_bytes:
                event = {
                    "type": event.get("type", "truncated"),
                    "stage": event.get("stage", ""),
                    "message": "事件内容过大，已截断",
                    "original_bytes": len(serialized),
                }
            record.events.append(event)
            record.updated_at = time.time()
            self._store.upsert(record)
            if event.get("type") == "error":
                raise RuntimeError(event.get("message", "诊断失败"))

    async def get(self, task_id: str) -> TaskRecord | None:
        row = self._store.load_one(task_id)
        if not row:
            return None
        record = self._record_from_row(row)
        self._tasks[task_id] = record
        return record

    async def cancel(self, task_id: str) -> bool:
        task = self._running.get(task_id)
        if task and not task.done() and config.inline_task_execution:
            task.cancel()
            return True
        return self._store.request_cancel(task_id)


diagnosis_task_manager = DiagnosisTaskManager()
