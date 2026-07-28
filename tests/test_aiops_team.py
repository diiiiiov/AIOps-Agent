import asyncio
from types import SimpleNamespace

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
