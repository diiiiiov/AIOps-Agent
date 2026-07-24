"""企业级请求中间件：追踪 ID、租户上下文和基础访问审计。"""

import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.audit import audit_event
from app.core.request_context import RequestContext, reset_request_context, set_request_context
from app.config import config
from app.security import has_role, verify_bearer_token
from app.core.metrics import metrics


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        claims = {}
        if config.auth_enabled and request.url.path.startswith("/api/"):
            try:
                claims = verify_bearer_token(request.headers.get("Authorization"))
                required_role = self._required_role(request)
                if required_role and not has_role(claims, required_role):
                    return JSONResponse(status_code=403, content={"detail": "无权执行此操作"})
            except Exception as exc:
                status_code = getattr(exc, "status_code", 401)
                detail = getattr(exc, "detail", "认证失败")
                return JSONResponse(status_code=status_code, content={"detail": detail})

        # 认证开启后只信任 JWT claims；关闭时保留开发环境上下文兼容性。
        context = RequestContext(
            request_id=request_id,
            tenant_id=claims.get("tenant_id", request.headers.get("X-Tenant-ID", config.default_tenant_id)),
            user_id=claims.get("sub", request.headers.get("X-User-ID", "anonymous")),
            roles=tuple(claims.get("roles", request.headers.get("X-Roles", "").split(","))),
        )
        token = set_request_context(context)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            metrics.increment("http_requests_total")
            metrics.increment(f"http_status_{response.status_code}_total")
            metrics.observe("http_request_duration_ms_total", (time.perf_counter() - started) * 1000)
            audit_event(
                "http.request",
                resource=request.url.path,
                outcome="success" if response.status_code < 400 else "failure",
                method=request.method,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_context(token)

    @staticmethod
    def _required_role(request: Request) -> str | None:
        if request.method == "POST" and request.url.path in {"/api/upload", "/api/index_directory"}:
            return "knowledge_admin"
        if request.url.path.startswith("/api/aiops"):
            return "operator"
        if request.url.path.startswith("/api/metrics"):
            return "admin"
        if request.url.path.startswith("/api/tool-approvals"):
            return "operator"
        if request.url.path.startswith("/api/chat"):
            return "viewer"
        return None
