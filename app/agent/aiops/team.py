"""Supervisor, specialist agents, and cross-validation nodes for AIOps."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send
from loguru import logger
from pydantic import BaseModel, Field

from app.agent.mcp_client import get_mcp_client_with_retry
from app.config import config
from app.core.model_router import model_router
from app.core.tool_gateway import tool_gateway
from app.core.tool_policy import filter_tools
from app.core.usage_tracker import record_message_usage
from app.tools import get_current_time, retrieve_knowledge

from .state import AgentAssignment, AgentResult, PlanExecuteState

SPECIALIST_NODE = "specialist"

AGENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "log": {
        "label": "日志 Agent",
        "task": "扫描故障时间窗内的日志与日志主题，提取错误模式、异常堆栈和时间相关性。",
        "tool_names": {
            "get_current_timestamp",
            "get_region_code_by_name",
            "get_topic_info_by_name",
            "search_topic_by_service_name",
            "search_log",
        },
        "model_setting": "aiops_log_model",
        "prompt": "你是日志取证专家。只根据日志证据提出根因假设，保留时间、服务和错误模式；不要把相关性写成因果性。",
    },
    "monitor": {
        "label": "监控 Agent",
        "task": "检查 CPU、内存及可用监控指标的趋势、突变和告警相关性。",
        "tool_names": {"query_cpu_metrics", "query_memory_metrics", "get_current_time"},
        "model_setting": "aiops_monitor_model",
        "prompt": "你是可观测性与指标专家。关注趋势、基线、峰值和时间对齐，明确指标能支持或反驳哪些根因。",
    },
    "knowledge": {
        "label": "知识 Agent",
        "task": "检索内部知识库、历史案例和处置手册，寻找可复用的根因模式与安全处置建议。",
        "tool_names": {"retrieve_knowledge"},
        "model_setting": "aiops_knowledge_model",
        "prompt": "你是运维知识与历史案例专家。区分当前事件证据和历史经验；经验只能形成候选假设，不能冒充现场事实。",
    },
}


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
    """Run one specialist with its own prompt, model, and tool allow-list."""

    assignment = state["assignment"]
    agent = assignment["agent"]
    definition = AGENT_DEFINITIONS[agent]
    model_name = model_name_for(agent)
    tools = await tools_for_agent(agent)
    llm = model_router.create(model=model_name, temperature=0)
    messages: list[Any] = [
        SystemMessage(
            content=dedent(
                f"""
                {definition['prompt']}
                你的工具权限仅限当前专业域。必须先收集证据，再给出一个可证伪的假设。
                禁止编造工具结果；证据不足时降低置信度，并列出缺失项。
                """
            ).strip()
        ),
        HumanMessage(content=assignment["task"]),
    ]

    try:
        if tools:
            tool_decision = await llm.bind_tools(tools).ainvoke(messages)
            record_message_usage(tool_decision, model_name)
            messages.append(tool_decision)
            if getattr(tool_decision, "tool_calls", None):
                messages.extend(await tool_gateway.execute_calls(tool_decision.tool_calls, tools))

        structured_llm = llm.with_structured_output(SpecialistHypothesis)
        hypothesis = await structured_llm.ainvoke(messages)
        # Some providers attach usage only to raw messages; this call is still valid without it.
        result: AgentResult = {
            "agent": agent,
            "task": assignment["task"],
            "hypothesis": hypothesis.hypothesis,
            "confidence": hypothesis.confidence,
            "evidence": hypothesis.evidence,
            "counter_evidence": hypothesis.counter_evidence,
            "recommended_actions": hypothesis.recommended_actions,
            "status": "completed",
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
        }

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
    messages = [
        SystemMessage(
            content=dedent(
                """
                你是 AIOps Supervisor 和根因仲裁者。交叉验证多个专业 Agent 的独立假设：
                1. 优先采信有现场证据且被不同数据源相互印证的结论；
                2. 明确指出冲突、反证、失败分支和仍缺失的证据；
                3. 历史知识不能替代现场日志或监控；不要用多数票代替证据权重；
                4. Markdown 报告必须包含“## 根因分析”章节，并包含：结论与置信度、
                   证据链、竞争假设/反证、处置建议、验证步骤；
                5. 不执行变更，只提出安全且可回滚的建议。证据不足时必须保留不确定性。
                """
            ).strip()
        ),
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
