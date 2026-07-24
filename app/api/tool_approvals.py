"""高风险工具审批与一次性执行 API。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import config
from app.core.audit import audit_event
from app.core.request_context import get_request_context
from app.core.tool_gateway import tool_gateway
from app.services.tool_approval_service import tool_approval_service
from app.agent.mcp_client import get_mcp_client_with_retry
from app.tools import get_current_time, retrieve_knowledge

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


@router.get("/tool-approvals")
async def list_approvals():
    return {"items": tool_approval_service.list(get_request_context().tenant_id)}


@router.post("/tool-approvals/{approval_id}/approve")
async def approve_tool(approval_id: str):
    context = get_request_context()
    if config.auth_enabled and "admin" not in context.roles:
        raise HTTPException(status_code=403, detail="只有管理员可以批准高风险操作")
    token = tool_approval_service.approve(
        approval_id, tenant_id=context.tenant_id, approver=context.user_id
    )
    if not token:
        raise HTTPException(status_code=409, detail="审批单不存在或状态不可批准")
    audit_event("tool.approve", resource=approval_id)
    return {"approval_id": approval_id, "execution_token": token, "single_use": True}


@router.post("/tool-approvals/{approval_id}/execute")
async def execute_approved_tool(approval_id: str, request: ToolExecuteRequest):
    records = [item for item in tool_approval_service.list(get_request_context().tenant_id)
               if item["approval_id"] == approval_id]
    if not records:
        raise HTTPException(status_code=404, detail="审批单不存在")
    record = records[0]
    import json
    args: Any = json.loads(record["args_json"])
    tools = [get_current_time, retrieve_knowledge] + list(
        await (await get_mcp_client_with_retry()).get_tools()
    )
    messages = await tool_gateway.execute_calls(
        [{"id": approval_id, "name": record["tool_name"], "args": args}], tools,
        approval_id=approval_id, approval_token=request.token,
        create_pending_approval=False,
    )
    content = messages[0].content if messages else "工具未返回结果"
    if "令牌无效" in str(content):
        raise HTTPException(status_code=403, detail="执行令牌无效或已使用")
    audit_event("tool.approved_execute", resource=record["tool_name"], approval_id=approval_id)
    return {"approval_id": approval_id, "status": "executed", "result": content}
