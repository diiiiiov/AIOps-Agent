"""模型用量与成本账本。"""

from collections import defaultdict
from threading import Lock
from typing import Any
from datetime import datetime

from app.core.request_context import get_request_context
from app.config import config
from app.core.usage_store import usage_store


class UsageTracker:
    def __init__(self) -> None:
        self._usage: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._lock = Lock()

    def record(self, *, model: str, input_tokens: int = 0, output_tokens: int = 0,
               estimated_cost: float | None = None) -> None:
        tenant = get_request_context().tenant_id
        if estimated_cost is None:
            estimated_cost = calculate_cost(model, input_tokens, output_tokens)
        usage_store.add(tenant, model, input_tokens, output_tokens, estimated_cost)
        with self._lock:
            item = self._usage[tenant]
            item["requests"] += 1
            item["input_tokens"] += input_tokens
            item["output_tokens"] += output_tokens
            item["estimated_cost"] += estimated_cost
            item[f"model:{model}:requests"] += 1

    def snapshot(self) -> dict[str, Any]:
        return usage_store.aggregate(self._month_start())

    def budget_exceeded(self) -> bool:
        """预算为 0 表示不限制；否则按当前进程账本执行硬阈值。"""
        if config.monthly_budget_usd <= 0:
            return False
        tenant = get_request_context().tenant_id
        usage = usage_store.aggregate(self._month_start()).get(tenant, {})
        return float(usage.get("estimated_cost", 0)) >= config.monthly_budget_usd

    @staticmethod
    def _month_start() -> float:
        now = datetime.now()
        return datetime(now.year, now.month, 1).timestamp()


usage_tracker = UsageTracker()


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """价格单位为美元/百万 Token。未知模型返回零并在运营侧显示待配置。"""
    price = config.llm_pricing.get(model, {})
    return (
        input_tokens * float(price.get("input", 0))
        + output_tokens * float(price.get("output", 0))
    ) / 1_000_000


def record_message_usage(message: Any, model: str) -> None:
    usage = getattr(message, "usage_metadata", None) or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    if input_tokens or output_tokens:
        usage_tracker.record(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
