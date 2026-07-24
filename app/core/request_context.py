"""请求级上下文：为审计、日志和多租户隔离提供统一入口。"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    request_id: str = "system"
    tenant_id: str = "public"
    user_id: str = "anonymous"
    roles: tuple[str, ...] = ()


_current_context: ContextVar[RequestContext] = ContextVar(
    "request_context", default=RequestContext()
)


def get_request_context() -> RequestContext:
    return _current_context.get()


def set_request_context(context: RequestContext):
    return _current_context.set(context)


def reset_request_context(token) -> None:
    _current_context.reset(token)
