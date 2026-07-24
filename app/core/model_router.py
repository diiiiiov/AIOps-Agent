"""运行时模型路由与热切换。"""

from threading import Lock
from typing import Any
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

from app.config import config
from app.core.audit import audit_event


class ModelRouter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._model = config.rag_model
        self._base_url = config.deepseek_base_url
        self._generation = 1

    @property
    def generation(self) -> int:
        return self._generation

    def snapshot(self) -> dict[str, Any]:
        return {
            "provider": config.llm_provider,
            "model": self._model,
            "base_url": self._base_url,
            "fallback_models": [item.strip() for item in config.llm_fallback_models.split(",") if item.strip()],
            "generation": self._generation,
        }

    def switch(self, *, model: str, base_url: str | None = None) -> dict[str, Any]:
        target_url = (base_url or self._base_url).rstrip("/")
        parsed = urlparse(target_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("模型地址必须使用白名单中的 HTTPS 地址")
        if target_url not in config.allowed_llm_base_urls:
            raise ValueError("模型地址不在 LLM_ALLOWED_BASE_URLS 白名单中")
        with self._lock:
            previous = self._model
            self._model = model.strip()
            self._base_url = target_url
            self._generation += 1
        audit_event("model.switch", resource=self._model, previous_model=previous)
        return self.snapshot()

    def create(self, *, temperature: float = 0, streaming: bool = False) -> ChatOpenAI:
        with self._lock:
            model, base_url = self._model, self._base_url
        return ChatOpenAI(
            model=model, api_key=config.deepseek_api_key, base_url=base_url,
            temperature=temperature, streaming=streaming,
        )


model_router = ModelRouter()
