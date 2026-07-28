"""Supervisor + professional-agent AIOps diagnosis service."""

from collections.abc import AsyncGenerator
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from loguru import logger

from app.agent.aiops import (
    PlanExecuteState,
    cross_validate,
    fan_out_specialists,
    specialist,
    supervisor,
)
from app.core.request_context import get_request_context
from app.models.aiops import DiagnosisContext
from app.services.diagnosis_prompt import build_diagnosis_task, extract_root_causes

# 节点名称常量
NODE_SUPERVISOR = "supervisor"
NODE_SPECIALIST = "specialist"
NODE_CROSS_VALIDATE = "cross_validate"


class AIOpsService:
    """Parallel AIOps team coordinated by a Supervisor."""

    def __init__(self):
        """初始化服务"""
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
        logger.info("Supervisor + Specialist Agents Service 初始化完成")

    def _build_graph(self):
        """Build Supervisor -> Send(fan-out) -> validation(fan-in)."""
        logger.info("构建工作流图...")

        # 创建状态图
        workflow = StateGraph(PlanExecuteState)

        # 添加节点
        workflow.add_node(NODE_SUPERVISOR, supervisor)
        workflow.add_node(NODE_SPECIALIST, specialist)
        workflow.add_node(NODE_CROSS_VALIDATE, cross_validate)

        # 设置入口点
        workflow.set_entry_point(NODE_SUPERVISOR)

        # 定义边
        workflow.add_conditional_edges(
            NODE_SUPERVISOR,
            fan_out_specialists,
            [NODE_SPECIALIST],
        )
        # LangGraph waits for all Send branches before running this downstream node.
        workflow.add_edge(NODE_SPECIALIST, NODE_CROSS_VALIDATE)
        workflow.add_edge(NODE_CROSS_VALIDATE, END)

        # 编译工作流
        compiled_graph = workflow.compile(checkpointer=self.checkpointer)

        logger.info("工作流图构建完成")
        return compiled_graph

    def set_checkpointer(self, checkpointer) -> None:
        """切换 Checkpointer 并重新编译诊断图。"""
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    async def execute(
        self,
        user_input: str,
        session_id: str = "default"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        执行 Supervisor 并行诊断与交叉验证流程

        Args:
            user_input: 用户的任务描述
            session_id: 会话ID

        Yields:
            Dict[str, Any]: 流式事件
        """
        logger.info(f"[会话 {session_id}] 开始执行任务: {user_input}")

        try:
            # 初始化状态
            initial_state: PlanExecuteState = {
                "input": user_input,
                "assignments": [],
                "agent_results": [],
                "plan": [],
                "past_steps": [],
                "response": "",
                "arbitration": {},
            }

            # 流式执行工作流
            config_dict = {
                "configurable": {
                    "thread_id": f"aiops:{get_request_context().tenant_id}:{session_id}"
                }
            }

            async for event in self.graph.astream(
                input=initial_state,
                config=config_dict,
                stream_mode="updates"
            ):
                # 解析事件
                for node_name, node_output in event.items():
                    logger.info(f"节点 '{node_name}' 输出事件")

                    # 根据节点类型生成不同的事件
                    if node_name == NODE_SUPERVISOR:
                        yield self._format_supervisor_event(node_output)
                    elif node_name == NODE_SPECIALIST:
                        yield self._format_specialist_event(node_output)
                    elif node_name == NODE_CROSS_VALIDATE:
                        yield self._format_validation_event(node_output)

            # 获取最终状态
            final_state = await self.graph.aget_state(config_dict)
            final_response = ""

            # 安全地获取响应（处理 values 可能为 None 的情况）
            final_values = final_state.values if final_state and final_state.values else {}
            final_response = final_values.get("response", "")
            agent_results = final_values.get("agent_results", [])
            arbitration = final_values.get("arbitration", {})

            # 发送完成事件
            yield {
                "type": "complete",
                "stage": "complete",
                "message": "任务执行完成",
                "response": final_response,
                "arbitration": arbitration,
                "evidence": [
                    {
                        "id": f"E{i}",
                        "step": step,
                        "observation": result,
                    }
                    for i, result in enumerate(agent_results, 1)
                    for step in [f"{result.get('agent', 'unknown')} Agent"]
                ]
            }

            logger.info(f"[会话 {session_id}] 任务执行完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] 任务执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "stage": "error",
                "message": f"任务执行出错: {str(e)}"
            }

    async def diagnose(
        self,
        session_id: str = "default",
        context: DiagnosisContext | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        AIOps 诊断接口（兼容旧接口）

        Args:
            session_id: 会话ID

        Yields:
            Dict[str, Any]: 诊断过程的流式事件
        """
        aiops_task = build_diagnosis_task(context)
        logger.info(
            f"[会话 {session_id}] 诊断模式: "
            f"{'指定事件' if context and context.model_dump(exclude_none=True) else '系统巡检'}"
        )

        async for event in self.execute(aiops_task, session_id):
            if event.get("type") == "complete":
                yield {
                    "type": "complete",
                    "stage": "diagnosis_complete",
                    "message": "诊断流程完成",
                    "diagnosis": {
                        "status": "completed",
                        "report": event.get("response", ""),
                        "root_causes": extract_root_causes(event.get("response", "")),
                        "context": context.model_dump(exclude_none=True) if context else {},
                        "evidence": event.get("evidence", []),
                        "arbitration": event.get("arbitration", {}),
                    }
                }
            else:
                yield event

    def _format_supervisor_event(self, state: dict | None) -> dict:
        """Format the Supervisor dispatch event using the legacy plan envelope."""
        if not state:
            return {
                "type": "status",
                "stage": "supervisor",
                "message": "Supervisor 正在分派专业调查任务"
            }

        assignments = state.get("assignments", [])

        return {
            "type": "plan",
            "stage": "team_dispatched",
            "message": f"Supervisor 已并行分派 {len(assignments)} 个专业 Agent",
            "plan": [item.get("task", "") for item in assignments],
            "agents": [item.get("agent", "") for item in assignments],
        }

    def _format_specialist_event(self, state: dict | None) -> dict:
        """Format one result emitted by a parallel specialist branch."""
        if not state:
            return {
                "type": "status",
                "stage": "specialist",
                "message": "专业 Agent 调查中"
            }

        results = state.get("agent_results", [])
        if results:
            result = results[-1]
            agent = result.get("agent", "unknown")
            return {
                "type": "step_complete",
                "stage": "specialist_complete",
                "message": f"{agent} Agent 调查完成",
                "current_step": result.get("task", ""),
                "evidence": {
                    "id": f"agent:{agent}",
                    "step": f"{agent} Agent",
                    "observation": result,
                },
                "result_preview": str(result.get("hypothesis", ""))[:500],
                "agent": agent,
                "confidence": result.get("confidence", 0),
            }
        return {"type": "status", "stage": "specialist", "message": "专业 Agent 调查中"}

    def _format_validation_event(self, state: dict | None) -> dict:
        """Format the cross-validation and arbitration event."""
        if not state:
            return {
                "type": "status",
                "stage": "cross_validation",
                "message": "Supervisor 正在交叉验证各 Agent 假设"
            }

        response = state.get("response", "")
        if response:
            return {
                "type": "report",
                "stage": "final_report",
                "message": "Supervisor 已完成交叉验证与仲裁",
                "report": response,
                "arbitration": state.get("arbitration", {}),
            }
        return {
            "type": "status",
            "stage": "cross_validation",
            "message": "Supervisor 正在交叉验证各 Agent 假设",
        }


# 全局单例
aiops_service = AIOpsService()
