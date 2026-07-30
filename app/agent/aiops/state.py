"""State definitions for the Supervisor + specialist AIOps graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentAssignment(TypedDict):
    """A bounded investigation delegated by the supervisor."""

    agent: str
    task: str


class AgentResult(TypedDict, total=False):
    """Evidence and hypothesis returned by one specialist."""

    agent: str
    task: str
    hypothesis: str
    confidence: float
    evidence: list[str]
    counter_evidence: list[str]
    recommended_actions: list[str]
    status: str
    error: str
    # ReAct 多轮工具调用追踪记录
    tool_calls: list[dict[str, Any]]
    iterations: int
    termination_reason: str


class PlanExecuteState(TypedDict, total=False):
    """Shared state kept under the legacy name for API compatibility."""

    input: str
    assignments: list[AgentAssignment]
    # Populated only in the private state sent to a specialist node.
    assignment: AgentAssignment
    # Fan-in reducer: every Send branch appends exactly one result.
    agent_results: Annotated[list[AgentResult], operator.add]
    response: str
    arbitration: dict[str, Any]

    # Legacy fields are retained so old checkpoints/readers can be migrated safely.
    plan: list[str]
    past_steps: Annotated[list[tuple[str, str]], operator.add]
