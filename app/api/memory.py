"""企业记忆管理 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.audit import audit_event
from app.core.request_context import get_request_context
from app.services.memory_service import memory_service
from app.config import config

router = APIRouter()


class MemoryCreate(BaseModel):
    tier: str = Field(pattern="^(tenant|shared)$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    ttl_seconds: int | None = Field(default=None, ge=60, le=31536000)


@router.post("/memories", status_code=201)
async def create_memory(request: MemoryCreate):
    context = get_request_context()
    roles = set(context.roles)
    if config.auth_enabled and request.tier == "shared" and "admin" not in roles:
        raise HTTPException(status_code=403, detail="只有管理员可以写入共享记忆")
    if config.auth_enabled and request.tier == "tenant" and not roles.intersection({"operator", "knowledge_admin", "admin"}):
        raise HTTPException(status_code=403, detail="无权写入租户记忆")
    memory_id = memory_service.remember(
        tier=request.tier, tenant_id=context.tenant_id, owner_id=context.user_id,
        title=request.title, content=request.content, ttl_seconds=request.ttl_seconds,
    )
    audit_event("memory.create", resource=memory_id, tier=request.tier, title=request.title)
    return {"memory_id": memory_id, "tier": request.tier}


@router.get("/memories")
async def list_memories(limit: int = 20):
    context = get_request_context()
    return {"items": memory_service.recall(tenant_id=context.tenant_id, limit=limit)}
