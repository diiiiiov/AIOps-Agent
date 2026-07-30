import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.aiops import team
from app.services import aiops_service as service_module


def test_supervisor_fans_out_all_professional_agents_with_send():
    update = team.supervisor({"input": "payment-api timeout"})
    sends = team.fan_out_specialists({"input": "payment-api timeout", **update})

    assert {send.arg["assignment"]["agent"] for send in sends} == {
        "log",
        "monitor",
        "knowledge",
    }
    assert all(send.node == team.SPECIALIST_NODE for send in sends)


async def test_specialists_have_independent_tool_sets(monkeypatch):
    class FakeClient:
        async def get_tools(self):
            return [
                SimpleNamespace(name="search_log"),
                SimpleNamespace(name="search_topic_by_service_name"),
                SimpleNamespace(name="query_cpu_metrics"),
                SimpleNamespace(name="query_memory_metrics"),
                SimpleNamespace(name="execute_remediation"),
            ]

    async def fake_client():
        return FakeClient()

    monkeypatch.setattr(team, "get_mcp_client_with_retry", fake_client)

    log_names = {team._tool_name(item) for item in await team.tools_for_agent("log")}
    monitor_names = {team._tool_name(item) for item in await team.tools_for_agent("monitor")}
    knowledge_names = {team._tool_name(item) for item in await team.tools_for_agent("knowledge")}

    assert log_names == {"search_log", "search_topic_by_service_name"}
    assert monitor_names == {"get_current_time", "query_cpu_metrics", "query_memory_metrics"}
    assert knowledge_names == {"retrieve_knowledge"}
    assert "execute_remediation" not in log_names | monitor_names | knowledge_names


async def test_graph_runs_send_branches_concurrently_and_fans_in(monkeypatch):
    active = 0
    max_active = 0

    async def fake_specialist(state):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        agent = state["assignment"]["agent"]
        return {
            "agent_results": [
                {
                    "agent": agent,
                    "task": state["assignment"]["task"],
                    "hypothesis": f"{agent}-hypothesis",
                    "confidence": 0.5,
                    "evidence": [agent],
                    "status": "completed",
                }
            ],
            "past_steps": [(agent, "done")],
        }

    async def fake_validate(state):
        agents = sorted(item["agent"] for item in state["agent_results"])
        return {"response": ",".join(agents), "arbitration": {"agents": agents}}

    monkeypatch.setattr(service_module, "specialist", fake_specialist)
    monkeypatch.setattr(service_module, "cross_validate", fake_validate)
    service = service_module.AIOpsService()

    result = await service.graph.ainvoke(
        {
            "input": "incident",
            "assignments": [],
            "agent_results": [],
            "plan": [],
            "past_steps": [],
            "response": "",
            "arbitration": {},
        },
        {"configurable": {"thread_id": "test-parallel"}},
    )

    assert max_active == 3
    assert sorted(item["agent"] for item in result["agent_results"]) == [
        "knowledge",
        "log",
        "monitor",
    ]
    assert result["response"] == "knowledge,log,monitor"


def test_agent_models_can_be_configured_independently(monkeypatch):
    monkeypatch.setattr(team.config, "aiops_log_model", "fast-model")
    monkeypatch.setattr(team.config, "aiops_monitor_model", "")
    monkeypatch.setattr(team.model_router, "snapshot", lambda: {"model": "default-model"})

    assert team.model_name_for("log") == "fast-model"
    assert team.model_name_for("monitor") == "default-model"


class _FakeBoundModel:
    def __init__(self, responses):
        self.responses = list(responses)

    async def ainvoke(self, messages):
        return self.responses.pop(0)


class _FakeStructuredModel:
    def __init__(self, parsed):
        self.parsed = parsed

    async def ainvoke(self, messages):
        return {
            "raw": AIMessage(
                content="structured",
                usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            ),
            "parsed": self.parsed,
            "parsing_error": None,
        }


class _FakeModel:
    def __init__(self, responses, parsed):
        self.bound = _FakeBoundModel(responses)
        self.parsed = parsed

    def bind_tools(self, tools):
        return self.bound

    def with_structured_output(self, schema, include_raw=False):
        assert include_raw is True
        return _FakeStructuredModel(self.parsed)


def _hypothesis():
    return team.SpecialistHypothesis(
        hypothesis="database saturation",
        confidence=0.8,
        evidence=["latency and errors aligned"],
        counter_evidence=[],
        recommended_actions=["verify pool usage"],
    )


async def test_specialist_runs_multi_turn_react_and_records_outcome(monkeypatch):
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_log", "args": {"query": "timeout"}, "id": "call-1"}],
            ),
            AIMessage(content="evidence is sufficient"),
        ],
        _hypothesis(),
    )

    async def fake_tools(agent):
        return [SimpleNamespace(name="search_log")]

    async def fake_execute(calls, tools):
        return [
            ToolMessage(
                content="timeout count=12",
                tool_call_id=calls[0]["id"],
                response_metadata={"status": "success", "duration_ms": 4.5},
            )
        ]

    usage_messages = []
    monkeypatch.setattr(team, "tools_for_agent", fake_tools)
    monkeypatch.setattr(team.model_router, "create", lambda **kwargs: model)
    monkeypatch.setattr(team.tool_gateway, "execute_calls", fake_execute)
    monkeypatch.setattr(team, "record_message_usage", lambda message, model_name: usage_messages.append(message))

    update = await team.specialist(
        {"assignment": {"agent": "log", "task": "investigate timeout"}}
    )
    result = update["agent_results"][0]

    assert result["status"] == "completed"
    assert result["iterations"] == 2
    assert result["termination_reason"] == "model_finished"
    assert result["tool_calls"][0]["status"] == "success"
    assert result["tool_calls"][0]["duration_ms"] == 4.5
    assert len(usage_messages) == 3  # two ReAct turns plus final structured output


async def test_specialist_blocks_repeated_tool_calls(monkeypatch):
    repeated = {"name": "search_log", "args": {"query": "same"}}
    model = _FakeModel(
        [
            AIMessage(content="", tool_calls=[{**repeated, "id": "call-1"}]),
            AIMessage(content="", tool_calls=[{**repeated, "id": "call-2"}]),
        ],
        _hypothesis(),
    )
    executed = []

    async def fake_tools(agent):
        return [SimpleNamespace(name="search_log")]

    async def fake_execute(calls, tools):
        executed.extend(calls)
        return [
            ToolMessage(
                content="same result",
                tool_call_id=call["id"],
                response_metadata={"status": "success", "duration_ms": 1.0},
            )
            for call in calls
        ]

    monkeypatch.setattr(team.config, "aiops_specialist_repeat_call_limit", 1)
    monkeypatch.setattr(team, "tools_for_agent", fake_tools)
    monkeypatch.setattr(team.model_router, "create", lambda **kwargs: model)
    monkeypatch.setattr(team.tool_gateway, "execute_calls", fake_execute)
    monkeypatch.setattr(team, "record_message_usage", lambda *args: None)

    update = await team.specialist(
        {"assignment": {"agent": "log", "task": "investigate timeout"}}
    )
    result = update["agent_results"][0]

    assert len(executed) == 1
    assert result["termination_reason"] == "repeated_tool_call"
    assert [item["status"] for item in result["tool_calls"]] == [
        "success",
        "duplicate_blocked",
    ]


async def test_specialist_enforces_total_tool_call_budget(monkeypatch):
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_log", "args": {"query": "one"}, "id": "call-1"},
                    {"name": "search_log", "args": {"query": "two"}, "id": "call-2"},
                ],
            )
        ],
        _hypothesis(),
    )
    executed = []

    async def fake_tools(agent):
        return [SimpleNamespace(name="search_log")]

    async def fake_execute(calls, tools):
        executed.extend(calls)
        return [
            ToolMessage(
                content="first result",
                tool_call_id=call["id"],
                response_metadata={"status": "success", "duration_ms": 1.0},
            )
            for call in calls
        ]

    monkeypatch.setattr(team.config, "aiops_specialist_max_tool_calls", 1)
    monkeypatch.setattr(team, "tools_for_agent", fake_tools)
    monkeypatch.setattr(team.model_router, "create", lambda **kwargs: model)
    monkeypatch.setattr(team.tool_gateway, "execute_calls", fake_execute)
    monkeypatch.setattr(team, "record_message_usage", lambda *args: None)

    update = await team.specialist(
        {"assignment": {"agent": "log", "task": "investigate timeout"}}
    )
    result = update["agent_results"][0]

    assert len(executed) == 1
    assert result["termination_reason"] == "max_tool_calls"
    assert [item["status"] for item in result["tool_calls"]] == [
        "success",
        "budget_exhausted",
    ]
