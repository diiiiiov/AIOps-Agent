"""Agent 工具调用网关：权限、审批、超时和审计。"""

import asyncio
import json
import time
from typing import Any

from langchain_core.messages import ToolMessage

from app.config import config
from app.core.audit import audit_event, redact
from app.core.request_context import get_request_context
from app.core.tool_policy import required_role
from app.services.tool_approval_service import tool_approval_service


class ToolGateway:
    @staticmethod
    def _message(
        content: str,
        call_id: str,
        *,
        status: str,
        duration_ms: float = 0.0,
    ) -> ToolMessage:
        return ToolMessage(
            content=content,
            tool_call_id=call_id,
            response_metadata={"status": status, "duration_ms": duration_ms},
        )

    async def execute_calls(
        self, calls: list[dict[str, Any]], tools: list[Any],
        approval_id: str | None = None, approval_token: str | None = None,
        create_pending_approval: bool = True,
    ) -> list[ToolMessage]:
        registry = {str(getattr(tool, "name", "")): tool for tool in tools}
        messages = []
        for call in calls:
            name = call.get("name", "")
            call_id = call.get("id", name)
            tool = registry.get(name)
            if not tool:
                messages.append(
                    self._message(f"工具不存在: {name}", call_id, status="not_found")
                )
                continue
            role = required_role(tool)
            context = get_request_context()
            if role == "admin":
                approved = bool(approval_id and approval_token and tool_approval_service.consume(
                    approval_id=approval_id, token=approval_token, tenant_id=context.tenant_id,
                    tool_name=name, args=call.get("args", {}),
                ))
                if not approved:
                    if not create_pending_approval:
                        messages.append(
                            self._message(
                                "审批令牌无效或已使用。", call_id, status="approval_denied"
                            )
                        )
                        continue
                    pending_id = tool_approval_service.create(
                        tenant_id=context.tenant_id, user_id=context.user_id,
                        tool_name=name, args=call.get("args", {}),
                    )
                    audit_event("tool.approval_required", resource=name, outcome="blocked", approval_id=pending_id)
                    messages.append(
                        self._message(
                            f"该工具属于高风险操作，需要人工审批。审批单: {pending_id}",
                            call_id,
                            status="approval_required",
                        )
                    )
                    continue
            started = time.perf_counter()
            status = "success"
            audit_event("tool.invoke", resource=name, args=redact(call.get("args", {})))
            try:
                result = await asyncio.wait_for(
                    tool.ainvoke(call.get("args", {})), timeout=config.tool_call_timeout_seconds
                )
                duration = round((time.perf_counter() - started) * 1000, 2)
                audit_event("tool.result", resource=name, duration_ms=duration, result=redact(result))
                content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            except TimeoutError:
                audit_event("tool.result", resource=name, outcome="timeout")
                content = f"工具调用超时（{config.tool_call_timeout_seconds} 秒）"
                duration = round((time.perf_counter() - started) * 1000, 2)
                status = "timeout"
            except Exception as exc:
                audit_event("tool.result", resource=name, outcome="failure", error=str(exc))
                content = f"工具调用失败: {exc}"
                duration = round((time.perf_counter() - started) * 1000, 2)
                status = "failure"
            messages.append(
                self._message(content, call_id, status=status, duration_ms=duration)
            )
        return messages


tool_gateway = ToolGateway()
