"""Supervisor, specialist agents, and cross-validation nodes for AIOps."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send
from loguru import logger
from pydantic import BaseModel, Field

from app.agent.mcp_client import get_mcp_client_with_retry
from app.agent.skill_loader import load_agent_definitions, load_prompt
from app.config import config
from app.core.model_router import model_router
from app.core.tool_gateway import tool_gateway
from app.core.tool_policy import filter_tools
from app.core.usage_tracker import record_message_usage
from app.tools import get_current_time, retrieve_knowledge

from .state import AgentAssignment, AgentResult, PlanExecuteState

SPECIALIST_NODE = "specialist"

# Agent 定义从 skills/agents/*.yaml 加载
AGENT_DEFINITIONS: dict[str, dict[str, Any]] = load_agent_definitions()


class SpecialistHypothesis(BaseModel):
    hypothesis: str = Field(description="最可能的根因假设；证据不足时明确写未知")
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class Arbitration(BaseModel):
    root_cause: str
    confidence: float = Field(ge=0, le=1)
    supporting_agents: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    report: str = Field(description="给用户的 Markdown 诊断报告")


def supervisor(state: PlanExecuteState) -> dict[str, Any]:
    """Create independent, bounded assignments for all professional agents."""

    incident = state.get("input", "")
    assignments: list[AgentAssignment] = [
        {
            "agent": name,
            "task": f"{definition['task']}\n事件：{incident}",
        }
        for name, definition in AGENT_DEFINITIONS.items()
    ]
    logger.info("Supervisor 已创建 {} 个并行调查任务", len(assignments))
    return {
        "assignments": assignments,
        "plan": [item["task"] for item in assignments],
    }


def fan_out_specialists(state: PlanExecuteState) -> list[Send]:
    """Use LangGraph Send to fan out one isolated state per specialist."""

    return [
        Send(
            SPECIALIST_NODE,
            {
                "input": state.get("input", ""),
                "assignment": assignment,
                "agent_results": [],
                "past_steps": [],
            },
        )
        for assignment in state.get("assignments", [])
    ]


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", "")))


async def tools_for_agent(agent: str) -> list[Any]:
    """Return only the tools owned by a specialist (least-privilege binding)."""

    definition = AGENT_DEFINITIONS[agent]
    candidates: list[Any] = [get_current_time, retrieve_knowledge]
    try:
        mcp_client = await get_mcp_client_with_retry()
        candidates.extend(await mcp_client.get_tools())
    except Exception as exc:
        logger.warning("{} 获取 MCP 工具失败，将使用可用本地工具: {}", agent, exc)

    allowed = definition["tool_names"]
    return filter_tools([tool for tool in candidates if _tool_name(tool) in allowed])


def model_name_for(agent: str) -> str:
    configured = str(getattr(config, AGENT_DEFINITIONS[agent]["model_setting"], "") or "").strip()
    return configured or str(model_router.snapshot()["model"])


async def specialist(state: PlanExecuteState) -> dict[str, Any]:
    """Run one specialist with its own prompt, model, and tool allow-list.

    Uses a ReAct (Reason → Act → Observe) loop: the LLM can call tools
    multiple times, inspecting each result before deciding the next action.
    """

    assignment = state["assignment"]
    agent = assignment["agent"]
    definition = AGENT_DEFINITIONS[agent]
    model_name = model_name_for(agent)
    tools = await tools_for_agent(agent)
    llm = model_router.create(model=model_name, temperature=0)
    specialist_template = load_prompt("specialist")
    specialist_prompt = specialist_template.format(definition_prompt=definition["prompt"])
    messages: list[Any] = [
        SystemMessage(content=specialist_prompt),
        HumanMessage(content=assignment["task"]),
    ]

    # 每个 agent 可在 YAML 中覆盖全局默认迭代上限
    max_iterations = definition.get("max_iterations") or config.aiops_specialist_max_iterations
    tool_call_log: list[dict[str, Any]] = []
    iterations_completed = 0

    try:
        if tools:
            bound_llm = llm.bind_tools(tools)
            for iteration in range(1, max_iterations + 1):
                response = await bound_llm.ainvoke(messages)
                record_message_usage(response, model_name)
                messages.append(response)
                iterations_completed = iteration

                tool_calls = getattr(response, "tool_calls", None)
                if not tool_calls:
                    logger.debug(
                        "{} ReAct 迭代 {}/{}: 无工具调用，进入假设生成",
                        definition["label"], iteration, max_iterations,
                    )
                    break

                logger.info(
                    "{} ReAct 迭代 {}/{}: 调用 {} 个工具 [{}]",
                    definition["label"], iteration, max_iterations,
                    len(tool_calls),
                    ", ".join(tc.get("name", "?") for tc in tool_calls),
                )
                tool_messages = await tool_gateway.execute_calls(tool_calls, tools)
                messages.extend(tool_messages)

                for tc in tool_calls:
                    tool_call_log.append({
                        "iteration": iteration,
                        "tool": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    })
            else:
                logger.warning(
                    "{} 达到最大 ReAct 迭代数 {}，强制进入假设生成",
                    definition["label"], max_iterations,
                )

        structured_llm = llm.with_structured_output(SpecialistHypothesis)
        hypothesis = await structured_llm.ainvoke(messages)
        result: AgentResult = {
            "agent": agent,
            "task": assignment["task"],
            "hypothesis": hypothesis.hypothesis,
            "confidence": hypothesis.confidence,
            "evidence": hypothesis.evidence,
            "counter_evidence": hypothesis.counter_evidence,
            "recommended_actions": hypothesis.recommended_actions,
            "status": "completed",
            "tool_calls": tool_call_log,
            "iterations": iterations_completed,
        }
    except Exception as exc:
        logger.error("{} 执行失败: {}", definition["label"], exc, exc_info=True)
        result = {
            "agent": agent,
            "task": assignment["task"],
            "hypothesis": "证据收集失败，无法形成可靠假设",
            "confidence": 0.0,
            "evidence": [],
            "counter_evidence": [],
            "recommended_actions": [],
            "status": "failed",
            "error": str(exc),
            "tool_calls": tool_call_log,
            "iterations": iterations_completed,
        }

    logger.info(
        "{} 调查完成: {} 轮迭代, {} 次工具调用, 置信度 {:.0%}",
        definition["label"], iterations_completed, len(tool_call_log),
        result.get("confidence", 0),
    )

    return {
        "agent_results": [result],
        "past_steps": [(definition["label"], json.dumps(result, ensure_ascii=False))],
    }


async def cross_validate(state: PlanExecuteState) -> dict[str, Any]:
    """Have the Supervisor challenge hypotheses and arbitrate conflicts."""

    results = state.get("agent_results", [])
    model_name = (config.aiops_supervisor_model or model_router.snapshot()["model"]).strip()
    llm = model_router.create(model=model_name, temperature=0)
    evidence_packet = json.dumps(results, ensure_ascii=False, indent=2)
    cross_validate_prompt = load_prompt("cross_validate")
    messages = [
        SystemMessage(content=cross_validate_prompt),
        HumanMessage(
            content=f"原始事件：\n{state.get('input', '')}\n\n各 Agent 假设：\n{evidence_packet}"
        ),
    ]
    try:
        arbitration = await llm.with_structured_output(Arbitration).ainvoke(messages)
        return {"response": arbitration.report, "arbitration": arbitration.model_dump()}
    except Exception as exc:
        logger.error("Supervisor 仲裁失败: {}", exc, exc_info=True)
        completed = [item for item in results if item.get("status") == "completed"]
        lines = ["# 诊断报告（降级模式）", "", "Supervisor 仲裁模型不可用，以下为未仲裁的专业 Agent 结果："]
        for item in completed:
            lines.extend(
                [
                    "",
                    f"## {AGENT_DEFINITIONS[item['agent']]['label']}",
                    f"- 假设：{item.get('hypothesis', '未知')}",
                    f"- 置信度：{float(item.get('confidence', 0)):.0%}",
                    f"- 证据：{'；'.join(item.get('evidence', [])) or '无'}",
                ]
            )
        lines.extend(["", f"> 仲裁失败：{exc}"])
        return {
            "response": "\n".join(lines),
            "arbitration": {"status": "degraded", "error": str(exc)},
        }
