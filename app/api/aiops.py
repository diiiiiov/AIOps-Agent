"""
AIOps 智能运维接口
"""

import json
from fastapi import APIRouter, Header, HTTPException
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.models.aiops import AIOpsRequest
from app.services.aiops_service import aiops_service
from app.services.task_manager import diagnosis_task_manager
from app.services.handoff_service import handoff_service
from app.core.request_context import get_request_context
from app.core.audit import audit_event
from pydantic import BaseModel, Field

router = APIRouter()


class HandoffRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class HandoffUpdate(BaseModel):
    status: str = Field(pattern="^(accepted|resolved|rejected)$")
    resolution: str | None = Field(default=None, max_length=4000)


@router.post("/aiops/tasks", status_code=202)
async def create_diagnosis_task(
    request: AIOpsRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """创建异步诊断任务；重复幂等键返回同一任务。"""
    try:
        record = await diagnosis_task_manager.submit(
            request.session_id or "default", request.context, idempotency_key
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {
        "task_id": record.task_id,
        "status": record.status,
        "attempts": record.attempts,
        "created_at": record.created_at,
    }


@router.get("/aiops/tasks/{task_id}")
async def get_diagnosis_task(task_id: str):
    record = await diagnosis_task_manager.get(task_id)
    if not record or record.tenant_id != get_request_context().tenant_id:
        raise HTTPException(status_code=404, detail="诊断任务不存在")
    return {
        "task_id": record.task_id,
        "status": record.status,
        "attempts": record.attempts,
        "events": record.events,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post("/aiops/tasks/{task_id}/cancel")
async def cancel_diagnosis_task(task_id: str):
    record = await diagnosis_task_manager.get(task_id)
    if not record or record.tenant_id != get_request_context().tenant_id:
        raise HTTPException(status_code=404, detail="诊断任务不存在")
    if not await diagnosis_task_manager.cancel(task_id):
        raise HTTPException(status_code=409, detail="任务不可取消或已结束")
    return {"task_id": task_id, "status": "cancelling"}


@router.post("/aiops/tasks/{task_id}/handoff", status_code=202)
async def request_handoff(task_id: str, request: HandoffRequest):
    task = await diagnosis_task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="诊断任务不存在")
    context = get_request_context()
    if task.tenant_id != context.tenant_id:
        raise HTTPException(status_code=404, detail="诊断任务不存在")
    await diagnosis_task_manager.cancel(task_id)
    record = handoff_service.create(
        task_id=task_id, tenant_id=context.tenant_id,
        user_id=context.user_id, reason=request.reason,
    )
    audit_event("handoff.request", resource=task_id, handoff_id=record["handoff_id"])
    return record


@router.get("/aiops/handoffs")
async def list_handoffs():
    return {"items": handoff_service.list(get_request_context().tenant_id)}


@router.patch("/aiops/handoffs/{handoff_id}")
async def update_handoff(handoff_id: str, request: HandoffUpdate):
    context = get_request_context()
    if not handoff_service.update(
        handoff_id, tenant_id=context.tenant_id, status=request.status, assigned_to=context.user_id,
        resolution=request.resolution,
    ):
        raise HTTPException(status_code=404, detail="接管记录不存在")
    audit_event("handoff.update", resource=handoff_id, status=request.status)
    return {"handoff_id": handoff_id, "status": request.status}


@router.post("/aiops")
async def diagnose_stream(request: AIOpsRequest):
    """
    AIOps 故障诊断接口（流式 SSE）

    **功能说明：**
    - 自动获取当前系统的活动告警
    - 使用 Plan-Execute-Replan 模式进行智能诊断
    - 流式返回诊断过程和结果

    **SSE 事件类型：**

    1. `status` - 状态更新
       ```json
       {
         "type": "status",
         "stage": "fetching_alerts",
         "message": "正在获取系统告警信息..."
       }
       ```

    2. `plan` - 诊断计划制定完成
       ```json
       {
         "type": "plan",
         "stage": "plan_created",
         "message": "诊断计划已制定，共 6 个步骤",
         "target_alert": {...},
         "plan": ["步骤1: ...", "步骤2: ..."]
       }
       ```

    3. `step_complete` - 步骤执行完成
       ```json
       {
         "type": "step_complete",
         "stage": "step_executed",
         "message": "步骤执行完成 (2/6)",
         "current_step": "查询系统日志",
         "result_preview": "...",
         "remaining_steps": 4
       }
       ```

    4. `report` - 最终诊断报告
       ```json
       {
         "type": "report",
         "stage": "final_report",
         "message": "最终诊断报告已生成",
         "report": "# 故障诊断报告\\n...",
         "evidence": {...}
       }
       ```

    5. `complete` - 诊断完成
       ```json
       {
         "type": "complete",
         "stage": "diagnosis_complete",
         "message": "诊断流程完成",
         "diagnosis": {...}
       }
       ```

    6. `error` - 错误信息
       ```json
       {
         "type": "error",
         "stage": "error",
         "message": "诊断过程发生错误: ..."
       }
       ```

    **使用示例：**
    ```bash
    curl -X POST "http://localhost:9900/api/aiops" \\
      -H "Content-Type: application/json" \\
      -d '{"session_id": "session-123"}' \\
      --no-buffer
    ```

    **前端使用示例：**
    ```javascript
    const eventSource = new EventSource('/api/aiops');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'plan') {
        console.log('诊断计划:', data.plan);
      } else if (data.type === 'step_complete') {
        console.log('步骤完成:', data.current_step);
      } else if (data.type === 'report') {
        console.log('最终报告:', data.report);
      } else if (data.type === 'complete') {
        console.log('诊断完成');
        eventSource.close();
      }
    };
    ```

    Args:
        request: AIOps 诊断请求

    Returns:
        SSE 事件流
    """
    session_id = request.session_id or "default"
    logger.info(f"[会话 {session_id}] 收到 AIOps 诊断请求（流式）")

    async def event_generator():
        try:
            async for event in aiops_service.diagnose(
                session_id=session_id,
                context=request.context,
            ):
                # 发送事件
                yield {
                    "event": "message",
                    "data": json.dumps(event, ensure_ascii=False)
                }

                # 如果是完成或错误事件，结束流
                if event.get("type") in ["complete", "error"]:
                    break

            logger.info(f"[会话 {session_id}] AIOps 诊断流式响应完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] AIOps 诊断流式响应异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "stage": "exception",
                    "message": f"诊断异常: {str(e)}"
                }, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())
