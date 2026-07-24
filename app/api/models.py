"""模型控制面 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import config
from app.core.model_router import model_router
from app.core.request_context import get_request_context

router = APIRouter()


class ModelSwitchRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)


@router.get("/models/current")
async def current_model():
    return model_router.snapshot()


@router.patch("/models/current")
async def switch_model(request: ModelSwitchRequest):
    if config.auth_enabled and "admin" not in get_request_context().roles:
        raise HTTPException(status_code=403, detail="只有管理员可以切换模型")
    try:
        return model_router.switch(model=request.model, base_url=request.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
