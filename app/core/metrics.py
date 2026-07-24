"""进程内指标注册表，提供 Prometheus 适配前的统一指标接口。"""

from collections import defaultdict
from threading import Lock
from typing import Any


class MetricsRegistry:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._values: dict[str, float] = defaultdict(float)
        self._lock = Lock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counts[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._values[name] += value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"counters": dict(self._counts), "totals": dict(self._values)}


metrics = MetricsRegistry()
