"""Supervisor, specialist agents, and cross-validation nodes for AIOps."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Send
from loguru import logger
from pydantic import BaseModel, Field

from app.agent.mcp_client import get_mcp_client_with_retry
from app.agent.skill_loader import load_agent_definitions, load_prompt
from app.config import config
from app.core.audit import redact
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


def _tool_call_fingerprint(call: dict[str, Any]) -> str:
    """Return a deterministic identity used to stop repeated tool calls."""

    return json.dumps(
        {"name": call.get("name", ""), "args": call.get("args", {})},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


async def _invoke_structured_with_usage(
    llm: Any,
    schema: type[BaseModel],
    messages: list[Any],
    model_name: str,
) -> BaseModel:
    """Invoke structured output while retaining the raw message for usage accounting."""

    payload = await llm.with_structured_output(schema, include_raw=True).ainvoke(messages)
    if isinstance(payload, dict) and "parsed" in payload:
        raw = payload.get("raw")
        if raw is not None:
            record_message_usage(raw, model_name)
        if payload.get("parsing_error") is not None:
            raise ValueError(f"结构化输出解析失败: {payload['parsing_error']}")
        parsed = payload.get("parsed")
        if parsed is None:
            raise ValueError("结构化输出为空")
        return parsed

    # Compatibility fallback for model adapters that ignore include_raw.
    record_message_usage(payload, model_name)
    return payload


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
    max_tool_calls = definition.get("max_tool_calls") or config.aiops_specialist_max_tool_calls
    repeat_call_limit = config.aiops_specialist_repeat_call_limit
    tool_call_log: list[dict[str, Any]] = []
    seen_calls: dict[str, int] = {}
    iterations_completed = 0
    total_tool_calls = 0
    termination_reason = "no_tools"

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
                    termination_reason = "model_finished"
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
                executable_calls: list[dict[str, Any]] = []
                blocked_messages: list[ToolMessage] = []
                blocked_records: list[dict[str, Any]] = []
                budget_exhausted = False

                for tc in tool_calls:
                    call_id = str(tc.get("id") or tc.get("name") or "tool")
                    base_record = {
                        "iteration": iteration,
                        "tool": tc.get("name", ""),
                        "args": redact(tc.get("args", {})),
                        "call_id": call_id,
                    }
                    fingerprint = _tool_call_fingerprint(tc)
                    previous_count = seen_calls.get(fingerprint, 0)

                    if total_tool_calls >= max_tool_calls:
                        budget_exhausted = True
                        blocked_messages.append(
                            ToolMessage(
                                content=f"工具调用总预算已用尽（最多 {max_tool_calls} 次）",
                                tool_call_id=call_id,
                                response_metadata={"status": "budget_exhausted", "duration_ms": 0.0},
                            )
                        )
                        blocked_records.append({**base_record, "status": "budget_exhausted"})
                        continue

                    if previous_count >= repeat_call_limit:
                        blocked_messages.append(
                            ToolMessage(
                                content="检测到重复工具调用，已阻止；请基于现有证据形成结论",
                                tool_call_id=call_id,
                                response_metadata={"status": "duplicate_blocked", "duration_ms": 0.0},
                            )
                        )
                        blocked_records.append({**base_record, "status": "duplicate_blocked"})
                        continue

                    seen_calls[fingerprint] = previous_count + 1
                    total_tool_calls += 1
                    executable_calls.append(tc)

                tool_messages = (
                    await tool_gateway.execute_calls(executable_calls, tools)
                    if executable_calls
                    else []
                )
                messages.extend(tool_messages)
                messages.extend(blocked_messages)

                for tc, tool_message in zip(executable_calls, tool_messages, strict=True):
                    metadata = tool_message.response_metadata or {}
                    tool_call_log.append(
                        {
                            "iteration": iteration,
                            "tool": tc.get("name", ""),
                            "args": redact(tc.get("args", {})),
                            "call_id": str(tc.get("id") or tc.get("name") or "tool"),
                            "status": metadata.get("status", "unknown"),
                            "duration_ms": metadata.get("duration_ms", 0.0),
                            "result": redact(tool_message.content, max_length=300),
                        }
                    )
                tool_call_log.extend(blocked_records)

                if budget_exhausted or total_tool_calls >= max_tool_calls:
                    termination_reason = "max_tool_calls"
                    break
                if not executable_calls and blocked_records:
                    termination_reason = "repeated_tool_call"
                    break
            else:
                termination_reason = "max_iterations"
                logger.warning(
                    "{} 达到最大 ReAct 迭代数 {}，强制进入假设生成",
                    definition["label"], max_iterations,
                )

        hypothesis = await _invoke_structured_with_usage(
            llm, SpecialistHypothesis, messages, model_name
        )
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
            "termination_reason": termination_reason,
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
            "termination_reason": "error",
        }

    logger.info(
        "{} 调查完成: {} 轮迭代, {} 次工具调用, 置信度 {:.0%}",
        definition["label"], iterations_completed, total_tool_calls,
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
        arbitration = await _invoke_structured_with_usage(llm, Arbitration, messages, model_name)
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
