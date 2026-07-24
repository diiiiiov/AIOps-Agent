"""结构化审计日志。

审计日志只记录元数据和脱敏后的摘要，不记录提示词、API Key 或完整业务数据。
生产环境可将同一事件适配到 Kafka、审计库或 SIEM。
"""

import json
from collections.abc import Mapping
from typing import Any

from loguru import logger

from app.core.request_context import get_request_context
from app.config import config


SENSITIVE_KEYS = {"password", "token", "api_key", "authorization", "secret", "content"}


def redact(value: Any, *, max_length: int = 500) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + "…"
    return value


def audit_event(action: str, *, resource: str = "", outcome: str = "success", **metadata: Any) -> None:
    if not config.audit_enabled:
        return
    context = get_request_context()
    event = {
        "event": "audit",
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "request_id": context.request_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "roles": list(context.roles),
        "metadata": redact(metadata),
    }
    logger.bind(audit=True).info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
