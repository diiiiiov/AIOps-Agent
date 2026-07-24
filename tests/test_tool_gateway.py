import asyncio

import pytest

from app.config import config
from app.core.tool_gateway import ToolGateway


class FakeTool:
    def __init__(self, name, result="ok", delay=0):
        self.name = name
        self.result = result
        self.delay = delay

    async def ainvoke(self, args):
        await asyncio.sleep(self.delay)
        return self.result


@pytest.mark.asyncio
async def test_high_risk_tool_requires_approval():
    gateway = ToolGateway()
    messages = await gateway.execute_calls(
        [{"id": "c1", "name": "restart_service", "args": {}}],
        [FakeTool("restart_service")],
    )
    assert "需要人工审批" in messages[0].content


@pytest.mark.asyncio
async def test_tool_timeout(monkeypatch):
    monkeypatch.setattr(config, "tool_call_timeout_seconds", 0.01)
    gateway = ToolGateway()
    messages = await gateway.execute_calls(
        [{"id": "c1", "name": "query_metrics", "args": {}}],
        [FakeTool("query_metrics", delay=0.1)],
    )
    assert "超时" in messages[0].content
