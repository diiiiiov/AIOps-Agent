"""Agent 工具暴露策略。

工具默认只读；名称包含变更/执行关键词的工具需要 operator，危险操作需要 admin。
实际生产部署应把策略迁移到数据库或策略服务，并按租户配置。
"""

from collections.abc import Iterable
from typing import Any

from app.config import config
from app.core.audit import audit_event
from app.core.request_context import get_request_context


HIGH_RISK_MARKERS = ("delete", "drop", "rollback", "restart", "scale", "execute", "write", "modify")
OPERATOR_MARKERS = ("query", "search", "metric", "log", "alert", "monitor", "diagnos")


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", tool))).lower()


def required_role(tool: Any) -> str:
    name = _tool_name(tool)
    if any(marker in name for marker in HIGH_RISK_MARKERS):
        return "admin"
    if any(marker in name for marker in OPERATOR_MARKERS):
        return "operator"
    return "viewer"


def filter_tools(tools: Iterable[Any]) -> list[Any]:
    context = get_request_context()
    roles = set(context.roles)
    # 未开启认证时保持开发环境兼容；开启认证后按最小权限过滤。
    if not config.auth_enabled or not roles:
        return list(tools)
    allowed = []
    for tool in tools:
        role = required_role(tool)
        role_order = {"viewer": 0, "operator": 1, "admin": 2}
        highest_role = max((role_order.get(item, -1) for item in roles), default=-1)
        if highest_role >= role_order[role]:
            allowed.append(tool)
        else:
            audit_event("tool.denied", resource=_tool_name(tool), outcome="denied", required_role=role)
    audit_event(
        "tool.policy",
        resource="agent",
        allowed_tools=[_tool_name(tool) for tool in allowed],
    )
    return allowed
