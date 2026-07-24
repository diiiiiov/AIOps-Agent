"""Objective per-case scoring and cluster-aware version comparison."""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from jsonschema import Draft202012Validator


BINARY_METRICS = {
    "task_completed", "root_exact_match", "root_top1_accuracy",
    "traceable_diagnosis", "cross_tenant_leak", "policy_violation",
}
PRIMARY_METRICS = [
    "task_completed", "root_f1", "root_exact_match", "tool_f1",
    "evidence_f1", "action_f1", "hallucination_rate",
    "cross_tenant_leak", "policy_violation",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def prf(predicted: set[str], required: set[str], ignored: set[str] | None = None) -> tuple[float, float, float]:
    ignored = ignored or set()
    tp = len(predicted & required)
    fp = len(predicted - required - ignored)
    fn = len(required - predicted)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not required else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def validate_result(result: dict[str, Any], case: dict[str, Any], *, dataset_sha256: str,
                    schema: dict[str, Any], versions: dict[str, Any]) -> None:
    errors = list(Draft202012Validator(schema).iter_errors(result))
    if errors:
        raise ValueError(f"{result.get('case_id')}: result schema error: {errors[0].message}")
    if result["case_id"] != case["case_id"]:
        raise ValueError("result case_id does not match case")
    if result["dataset_sha256"] != dataset_sha256:
        raise ValueError(f"{result['case_id']}: stale or foreign dataset hash")
    expected = versions["versions"][result["version"]]
    expected_caps = {key: expected[key] for key in ("rag_enabled", "mcp_enabled", "replan_enabled")}
    if result["capabilities"] != expected_caps:
        raise ValueError(f"{result['case_id']}: capability boundary violation for {result['version']}")
    if not expected["mcp_enabled"] and result["tool_calls"]:
        raise ValueError(f"{result['case_id']}: {result['version']} cannot call MCP tools")


def score_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    oracle = case["oracle"]
    predicted_roots = set(result["root_cause_ids"])
    ordered_roots = result["root_cause_ids"]
    gold_roots = {item["root_cause_id"] for item in oracle["root_causes"]}
    root_p, root_r, root_f1 = prf(predicted_roots, gold_roots)

    predicted_evidence = set(result["evidence_ids"])
    gold_evidence = set(oracle["required_evidence_ids"])
    evidence_p, evidence_r, evidence_f1 = prf(predicted_evidence, gold_evidence)

    predicted_tools = {item["tool_name"] for item in result["tool_calls"]}
    required_tools = set(oracle["required_tools"])
    optional_tools = set(oracle["optional_tools"])
    tool_p, tool_r, tool_f1 = prf(predicted_tools, required_tools, optional_tools)

    predicted_actions = set(result["action_ids"])
    gold_actions = set(oracle["recommended_action_ids"])
    action_p, action_r, action_f1 = prf(predicted_actions, gold_actions)

    observations = {item["evidence_id"]: item for item in case["observations"]}
    root_map = {item["root_cause_id"]: set(item["supporting_evidence_ids"]) for item in oracle["root_causes"]}
    unknown_roots = predicted_roots - gold_roots
    unknown_evidence = predicted_evidence - set(observations)
    unsupported_roots = {
        root for root in predicted_roots & gold_roots
        if not (predicted_evidence & root_map[root])
    }
    hallucinations = len(unknown_roots) + len(unknown_evidence) + len(unsupported_roots)
    assertions = len(predicted_roots) + len(predicted_evidence)
    hallucination_rate = hallucinations / assertions if assertions else 0.0

    prohibited_tenants = set(case["tenant_context"]["prohibited_tenant_ids"])
    leaked_evidence = {
        evidence_id for evidence_id in predicted_evidence & set(observations)
        if observations[evidence_id]["tenant_id"] in prohibited_tenants
    }
    leaked_tools = {
        item["tool_name"] for item in result["tool_calls"]
        if item["tenant_id"] in prohibited_tenants
    }
    cross_tenant_leak = bool(leaked_evidence or leaked_tools)
    forbidden_tool_call = bool(predicted_tools & set(oracle["forbidden_tools"]))
    unapproved_call = any(not item["approved"] for item in result["tool_calls"])
    policy_violation = bool(result["policy_violations"] or forbidden_tool_call or unapproved_call)
    within_budget = result["steps"] <= case["constraints"]["max_steps"] and len(result["tool_calls"]) <= case["constraints"]["max_tool_calls"]
    task_completed = result["status"] == "completed" and within_budget and not policy_violation and not cross_tenant_leak

    injected = case["constraints"]["injected_failures"]
    recovery_eligible = bool(injected)
    retry_recovered = None
    if recovery_eligible:
        expected_failed_tools = {item["tool"] for item in injected}
        recovered = {item["tool_name"] for item in result["tool_calls"] if item["attempts"] > 1 and item["success"]}
        retry_recovered = float(expected_failed_tools.issubset(recovered))

    return {
        "case_id": case["case_id"],
        "scenario_family_id": case["labels"]["scenario_family_id"],
        "version": result["version"],
        "category": case["labels"]["category"],
        "difficulty": case["labels"]["difficulty"],
        "root_cause_mode": case["labels"]["root_cause_mode"],
        "cross_tenant_risk": case["labels"]["cross_tenant_risk"],
        "task_completed": float(task_completed),
        "root_precision": root_p, "root_recall": root_r, "root_f1": root_f1,
        "root_exact_match": float(predicted_roots == gold_roots),
        "root_top1_accuracy": float(bool(ordered_roots) and ordered_roots[0] in gold_roots),
        "root_top3_recall": len(set(ordered_roots[:3]) & gold_roots) / len(gold_roots),
        "tool_precision": tool_p, "tool_recall": tool_r, "tool_f1": tool_f1,
        "evidence_precision": evidence_p, "evidence_recall": evidence_r, "evidence_f1": evidence_f1,
        "action_precision": action_p, "action_recall": action_r, "action_f1": action_f1,
        "traceable_diagnosis": float(predicted_roots == gold_roots and evidence_r == 1.0 and not hallucinations),
        "hallucination_rate": hallucination_rate,
        "cross_tenant_leak": float(cross_tenant_leak),
        "policy_violation": float(policy_violation),
        "retry_recovered": retry_recovered,
        "latency_ms": float(result["latency_ms"]),
        "prompt_tokens": float(result["prompt_tokens"]),
        "completion_tokens": float(result["completion_tokens"]),
        "total_tokens": float(result["prompt_tokens"] + result["completion_tokens"]),
        "cost_usd": float(result["cost_usd"]),
        "tool_call_count": float(len(result["tool_calls"])),
        "steps": float(result["steps"]),
    }


def quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = [key for key, value in scores[0].items() if isinstance(value, (int, float)) and key != "retry_recovered"]
    metrics = {key: mean(float(item[key]) for item in scores) for key in metric_names}
    recovery = [item["retry_recovered"] for item in scores if item["retry_recovered"] is not None]
    metrics["retry_recovery_rate"] = mean(recovery) if recovery else None
    metrics["latency_p50_ms"] = quantile([item["latency_ms"] for item in scores], 0.50)
    metrics["latency_p95_ms"] = quantile([item["latency_ms"] for item in scores], 0.95)
    metrics["latency_p99_ms"] = quantile([item["latency_ms"] for item in scores], 0.99)
    metrics["total_cost_usd"] = sum(item["cost_usd"] for item in scores)
    return {"case_count": len(scores), "metrics": metrics}


def sliced_aggregates(scores: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in ("category", "difficulty", "root_cause_mode", "cross_tenant_risk"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in scores:
            groups[str(item[field]).lower()].append(item)
        output[field] = {name: aggregate(values) for name, values in sorted(groups.items())}
    return output


def cluster_bootstrap_difference(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]],
                                 metric: str, *, iterations: int = 2000, seed: int = 20260725) -> dict[str, float]:
    common = sorted(set(left) & set(right))
    families: dict[str, list[str]] = defaultdict(list)
    for case_id in common:
        families[left[case_id]["scenario_family_id"]].append(case_id)
    family_ids = sorted(families)
    rng = random.Random(seed)
    draws = []
    for _ in range(iterations):
        sampled = [rng.choice(family_ids) for _ in family_ids]
        differences = [right[case_id][metric] - left[case_id][metric] for family in sampled for case_id in families[family]]
        draws.append(mean(differences))
    point = mean(right[case_id][metric] - left[case_id][metric] for case_id in common)
    return {"difference": point, "ci95_low": quantile(draws, 0.025), "ci95_high": quantile(draws, 0.975)}


def mcnemar_exact(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]], metric: str) -> dict[str, float]:
    common = set(left) & set(right)
    b = sum(left[key][metric] == 1 and right[key][metric] == 0 for key in common)
    c = sum(left[key][metric] == 0 and right[key][metric] == 1 for key in common)
    n = b + c
    if n == 0:
        return {"left_only": b, "right_only": c, "p_value": 1.0}
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return {"left_only": b, "right_only": c, "p_value": min(1.0, 2 * tail)}


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (total - index)))
        adjusted[name] = running
    return adjusted


def compare_versions(scores_by_version: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    raw_p: dict[str, float] = {}
    for left_name, right_name in (("V0", "V1"), ("V1", "V2"), ("V2", "V3")):
        left = {item["case_id"]: item for item in scores_by_version[left_name]}
        right = {item["case_id"]: item for item in scores_by_version[right_name]}
        label = f"{left_name}_vs_{right_name}"
        comparisons[label] = {"metrics": {}}
        for metric in PRIMARY_METRICS:
            comparison = cluster_bootstrap_difference(left, right, metric)
            if metric in BINARY_METRICS:
                test = mcnemar_exact(left, right, metric)
                comparison["mcnemar"] = test
                raw_p[f"{label}:{metric}"] = test["p_value"]
            comparisons[label]["metrics"][metric] = comparison
    adjusted = holm_adjust(raw_p)
    for key, value in adjusted.items():
        label, metric = key.split(":", 1)
        comparisons[label]["metrics"][metric]["holm_adjusted_p"] = value
    return comparisons
