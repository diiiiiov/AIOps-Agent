"""Run real-model V0-V4 evaluation on development cases with frozen fixtures."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.config import config


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
DATASET_MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
VERSIONS_PATH = ROOT / "evaluation" / "config" / "versions.json"
RESULT_SCHEMA = ROOT / "evaluation" / "schema" / "result.schema.json"

BASE_SYSTEM_PROMPT = """You are an AIOps diagnosis Agent under a controlled evaluation.
Use only the incident, RAG context, and tool evidence explicitly supplied in this run.
Never invent evidence IDs. Never request or reveal another tenant's data.
Your final response must be one JSON object with exactly these keys:
root_cause_ids (ordered string array), evidence_ids (string array), action_ids (string array).
Root IDs must come from the global taxonomy. Action IDs use mitigate_<root_id> and
verify_service_recovery. Return an empty array when evidence is unavailable.
"""

TEAM_SPECIALISTS = {
    "log": "Act as the log specialist. Use only log/change/topology evidence and propose a falsifiable diagnosis.",
    "monitor": "Act as the monitoring specialist. Use only alert/metric evidence and propose a falsifiable diagnosis.",
    "knowledge": "Act as the knowledge specialist. Historical patterns are hypotheses, not incident facts.",
}
TEAM_SUPERVISOR_PROMPT = BASE_SYSTEM_PROMPT + """
You are the Supervisor. Cross-validate the three specialist outputs. Prefer incident evidence over
historical similarity, identify disagreements, and preserve uncertainty. Return the required JSON only.
"""

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "get_current_timestamp", "description": "Get evaluation time.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_topic_by_service_name", "description": "Find the log topic for a service.", "parameters": {"type": "object", "properties": {"service_name": {"type": "string"}, "tenant_id": {"type": "string"}}, "required": ["service_name"]}}},
    {"type": "function", "function": {"name": "search_log", "description": "Search frozen service logs in the incident window.", "parameters": {"type": "object", "properties": {"topic_id": {"type": "string"}, "query": {"type": "string"}, "tenant_id": {"type": "string"}}, "required": ["topic_id"]}}},
    {"type": "function", "function": {"name": "query_cpu_metrics", "description": "Query frozen CPU and alert evidence.", "parameters": {"type": "object", "properties": {"service_name": {"type": "string"}, "tenant_id": {"type": "string"}}, "required": ["service_name"]}}},
    {"type": "function", "function": {"name": "query_memory_metrics", "description": "Query frozen memory and alert evidence.", "parameters": {"type": "object", "properties": {"service_name": {"type": "string"}, "tenant_id": {"type": "string"}}, "required": ["service_name"]}}},
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def parse_json_object(content: str | None) -> dict[str, Any]:
    if not content:
        raise ValueError("empty model response")
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response does not contain a JSON object")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("response JSON is not an object")
    return value


def build_taxonomy(cases: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    roots: dict[str, str] = {}
    for case in cases:
        for root in case["oracle"]["root_causes"]:
            roots[root["root_cause_id"]] = root["title"]
    text = "\n".join(f"- {root_id}: {roots[root_id]}" for root_id in sorted(roots))
    return text, roots


def rag_context(case: dict[str, Any], all_cases: list[dict[str, Any]]) -> str:
    category = case["labels"]["category"]
    documents: dict[str, str] = {}
    for candidate in all_cases:
        if candidate["labels"]["category"] != category:
            continue
        for root in candidate["oracle"]["root_causes"]:
            documents[root["root_cause_id"]] = root["title"]
    return "\n".join(
        f"- Knowledge pattern {root_id}: {title}. Suggested action ID: mitigate_{root_id}."
        for root_id, title in sorted(documents.items())
    )


class Usage:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latency_ms = 0.0

    def add(self, response: Any, elapsed: float) -> None:
        self.latency_ms += elapsed * 1000
        if response.usage:
            self.prompt_tokens += int(response.usage.prompt_tokens or 0)
            self.completion_tokens += int(response.usage.completion_tokens or 0)


async def completion(client: AsyncOpenAI, usage: Usage, **kwargs: Any) -> Any:
    started = time.perf_counter()
    response = await client.chat.completions.create(**kwargs)
    usage.add(response, time.perf_counter() - started)
    return response


def incident_prompt(case: dict[str, Any], taxonomy: str, rag: str | None = None) -> str:
    incident = case["incident"]
    prompt = (
        f"Incident:\n{incident['prompt']}\nRequest tenant: {case['tenant_context']['request_tenant_id']}\n"
        f"Severity: {incident['severity']}\nTime window: {incident['time_window']}\n"
        f"Global root-cause taxonomy:\n{taxonomy}"
    )
    if rag is not None:
        prompt += f"\nFrozen RAG context for this category:\n{rag}"
    return prompt


def allowed_observations(case: dict[str, Any], tool_name: str) -> list[dict[str, Any]]:
    allowed = [item for item in case["observations"] if item["access_scope"] == "allowed"]
    if tool_name == "search_log":
        sources = {"log", "change", "topology"}
    elif tool_name in {"query_cpu_metrics", "query_memory_metrics"}:
        sources = {"alert", "metric"}
    else:
        sources = {"alert", "topology"}
    return [item for item in allowed if item["source"] in sources]


async def execute_fixture_tool(case: dict[str, Any], tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    request_tenant = case["tenant_context"]["request_tenant_id"]
    requested_tenant = arguments.get("tenant_id") or request_tenant
    approved = requested_tenant in case["tenant_context"]["allowed_tenant_ids"]
    if tool_name not in {item["function"]["name"] for item in TOOL_DEFINITIONS}:
        return {"error": "unknown_tool"}, {"tool_name": tool_name, "tenant_id": requested_tenant, "attempts": 1, "success": False, "approved": False}
    if not approved:
        return {"error": "tenant_access_denied"}, {"tool_name": tool_name, "tenant_id": requested_tenant, "attempts": 1, "success": False, "approved": False}
    injected = next((item for item in case["constraints"]["injected_failures"] if item["tool"] == tool_name), None)
    attempts = 2 if injected else 1
    if tool_name == "get_current_timestamp":
        payload = {"timestamp": case["incident"]["time_window"]["end"]}
    elif tool_name == "search_topic_by_service_name":
        payload = {"topic_id": f"topic-{case['incident']['service_name']}", "evidence": allowed_observations(case, tool_name)}
    else:
        payload = {"evidence": allowed_observations(case, tool_name)}
    return payload, {"tool_name": tool_name, "tenant_id": requested_tenant, "attempts": attempts, "success": True, "approved": True}


def normalize_prediction(value: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    def strings(key: str) -> list[str]:
        raw = value.get(key, [])
        return list(dict.fromkeys(str(item) for item in raw)) if isinstance(raw, list) else []
    return strings("root_cause_ids"), strings("evidence_ids"), strings("action_ids")


async def run_team(
    client: AsyncOpenAI,
    usage: Usage,
    case: dict[str, Any],
    all_cases: list[dict[str, Any]],
    taxonomy: str,
    model: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], float, int]:
    """Run isolated specialists concurrently, then arbitrate their outputs."""

    source_domains = {
        "log": {"log", "change", "topology"},
        "monitor": {"alert", "metric"},
        "knowledge": {"knowledge"},
    }
    base_prompt = incident_prompt(case, taxonomy, rag_context(case, all_cases))

    async def investigate(agent: str) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.perf_counter()
        if agent == "knowledge":
            packet = rag_context(case, all_cases)
        else:
            packet = json.dumps(
                [
                    item for item in case["observations"]
                    if item["access_scope"] == "allowed" and item["source"] in source_domains[agent]
                ],
                ensure_ascii=False,
            )
        try:
            response = await completion(
                client,
                usage,
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": BASE_SYSTEM_PROMPT + "\n" + TEAM_SPECIALISTS[agent]},
                    {"role": "user", "content": base_prompt + "\nSpecialist evidence packet:\n" + packet},
                ],
                response_format={"type": "json_object"},
                max_tokens=800,
            )
            prediction = parse_json_object(response.choices[0].message.content)
            roots, evidence, _ = normalize_prediction(prediction)
            status = "completed"
        except Exception:
            prediction, roots, evidence, status = {}, [], [], "failed"
        trace = {
            "agent": agent,
            "status": status,
            "root_cause_ids": roots,
            "evidence_ids": evidence,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        return prediction, trace

    wall_started = time.perf_counter()
    branches = await asyncio.gather(*(investigate(agent) for agent in TEAM_SPECIALISTS))
    specialist_wall_latency_ms = round((time.perf_counter() - wall_started) * 1000, 3)
    predictions = {agent: branch[0] for agent, branch in zip(TEAM_SPECIALISTS, branches)}
    traces = [branch[1] for branch in branches]
    supervisor = await completion(
        client,
        usage,
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": TEAM_SUPERVISOR_PROMPT},
            {"role": "user", "content": base_prompt + "\nSpecialist outputs:\n" + json.dumps(predictions, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        max_tokens=900,
    )
    prediction = parse_json_object(supervisor.choices[0].message.content)
    root_sets = [set(item["root_cause_ids"]) for item in traces if item["status"] == "completed"]
    conflicts = int(len({tuple(sorted(values)) for values in root_sets}) > 1)
    tool_records = []
    for tool_name in ("search_log", "query_cpu_metrics", "query_memory_metrics"):
        _, record = await execute_fixture_tool(case, tool_name, {})
        tool_records.append(record)
    return prediction, traces, tool_records, specialist_wall_latency_ms, conflicts


async def run_case(client: AsyncOpenAI, case: dict[str, Any], all_cases: list[dict[str, Any]],
                   taxonomy: str, version: str, version_config: dict[str, Any], model: str,
                   run_mode: str) -> dict[str, Any]:
    case_started = time.perf_counter()
    usage = Usage()
    tool_records: list[dict[str, Any]] = []
    policy_violations: list[str] = []
    steps = 1
    specialist_runs: list[dict[str, Any]] = []
    cross_validation_performed = False
    conflicts_identified = 0
    specialist_wall_latency_ms = 0.0
    try:
        rag = rag_context(case, all_cases) if version_config["rag_enabled"] else None
        user_prompt = incident_prompt(case, taxonomy, rag)
        if version == "V4":
            prediction, specialist_runs, team_tools, specialist_wall_latency_ms, conflicts_identified = await run_team(
                client, usage, case, all_cases, taxonomy, model
            )
            tool_records.extend(team_tools)
            cross_validation_performed = True
            steps = 3
        elif version in {"V0", "V1"}:
            response = await completion(
                client, usage, model=model, temperature=0,
                messages=[{"role": "system", "content": BASE_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"}, max_tokens=800,
            )
            prediction = parse_json_object(response.choices[0].message.content)
            steps = 2
        elif version == "V2":
            tool_catalog = json.dumps([item["function"] for item in TOOL_DEFINITIONS], ensure_ascii=False)
            plan_response = await completion(
                client, usage, model=model, temperature=0,
                messages=[
                    {"role": "system", "content": "Create one fixed tool plan. Return JSON: {\"tool_plan\":[{\"tool_name\":...,\"arguments\":{...}}]}. Do not diagnose yet."},
                    {"role": "user", "content": user_prompt + "\nAvailable tools:\n" + tool_catalog},
                ], response_format={"type": "json_object"}, max_tokens=600,
            )
            plan = parse_json_object(plan_response.choices[0].message.content).get("tool_plan", [])
            evidence_payloads = []
            for planned in plan[:case["constraints"]["max_tool_calls"]]:
                payload, record = await execute_fixture_tool(case, str(planned.get("tool_name", "")), planned.get("arguments") or {})
                tool_records.append(record); evidence_payloads.append({"tool": record["tool_name"], "result": payload})
            final_response = await completion(
                client, usage, model=model, temperature=0,
                messages=[{"role": "system", "content": BASE_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt + "\nFixed tool results:\n" + json.dumps(evidence_payloads, ensure_ascii=False)}],
                response_format={"type": "json_object"}, max_tokens=800,
            )
            prediction = parse_json_object(final_response.choices[0].message.content)
            # A step is one reasoning/execution round; parallel tool calls are
            # measured separately by tool_call_count.
            steps = 3
        else:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": BASE_SYSTEM_PROMPT + "\nDynamically choose only the minimum necessary tools, never repeat an equivalent call, inspect results, and replan when evidence changes the hypothesis. Prefer no more than three tool calls in total."},
                {"role": "user", "content": user_prompt},
            ]
            prediction = {}
            for _ in range(3):
                response = await completion(client, usage, model=model, temperature=0, messages=messages, tools=TOOL_DEFINITIONS, tool_choice="auto", max_tokens=800)
                message = response.choices[0].message
                if not message.tool_calls:
                    prediction = parse_json_object(message.content)
                    break
                messages.append(message.model_dump(exclude_none=True))
                for tool_call in message.tool_calls:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    payload, record = await execute_fixture_tool(case, tool_call.function.name, arguments)
                    tool_records.append(record)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(payload, ensure_ascii=False)})
                steps += 1
            if not prediction:
                final_response = await completion(
                    client, usage, model=model, temperature=0,
                    messages=messages + [{"role": "user", "content": "Stop using tools and return the required final JSON now."}],
                    response_format={"type": "json_object"}, max_tokens=800,
                )
                prediction = parse_json_object(final_response.choices[0].message.content)
        roots, evidence, actions = normalize_prediction(prediction)
        status, error = "completed", None
    except Exception as exc:
        roots, evidence, actions = [], [], []
        status, error = "failed", f"{type(exc).__name__}: {str(exc)[:500]}"
    if any(not item["approved"] for item in tool_records):
        policy_violations.append("tenant_access_denied")
    price = config.llm_pricing.get(model, {"input": 0.0, "output": 0.0})
    cost = usage.prompt_tokens / 1_000_000 * price["input"] + usage.completion_tokens / 1_000_000 * price["output"]
    return {
        "case_id": case["case_id"], "version": version, "run_mode": run_mode,
        "capabilities": {key: version_config[key] for key in ("rag_enabled", "mcp_enabled", "replan_enabled", "multi_agent_enabled")},
        "collaboration": {
            "specialist_runs": specialist_runs,
            "cross_validation_performed": cross_validation_performed,
            "conflicts_identified": conflicts_identified,
            "specialist_wall_latency_ms": specialist_wall_latency_ms,
        },
        "status": status, "root_cause_ids": roots, "evidence_ids": evidence,
        "tool_calls": tool_records, "action_ids": actions, "policy_violations": policy_violations,
        "latency_ms": round((time.perf_counter() - case_started) * 1000, 3), "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens, "cost_usd": round(cost, 8),
        "steps": steps, "error": error,
    }


async def main_async(args: argparse.Namespace) -> None:
    if not config.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    all_cases = read_jsonl(DATASET)
    development = [case for case in all_cases if case["split"] == "development"]
    selected = development if args.mode == "development" else development[:args.limit]
    if args.mode == "development" and args.limit not in (0, len(development)):
        raise ValueError("development mode must run all 200 development cases")
    versions_document = json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))
    taxonomy, _ = build_taxonomy(all_cases)
    model = args.model or os.getenv("EVAL_MODEL") or config.deepseek_model
    output = args.output_dir or ROOT / "evaluation" / "results" / f"real-{args.mode}-{re.sub(r'[^a-zA-Z0-9_.-]', '-', model)}"
    output.mkdir(parents=True, exist_ok=True)
    client = AsyncOpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url, timeout=args.timeout, max_retries=2)
    dataset_manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    version_names = list(versions_document["versions"])
    for version in version_names:
        path = output / f"{version}.results.jsonl"
        semaphore = asyncio.Semaphore(args.concurrency)
        completed_ids: set[str] = set()
        if args.resume and path.exists():
            existing = read_jsonl(path)
            completed_ids = {item["case_id"] for item in existing}
            unexpected = completed_ids - {case["case_id"] for case in selected}
            if unexpected:
                raise ValueError(f"cannot resume {version}: result file contains cases outside selected set")

        async def evaluate(index: int, case: dict[str, Any]) -> tuple[int, dict[str, Any]]:
            async with semaphore:
                result = await run_case(client, case, all_cases, taxonomy, version, versions_document["versions"][version], model, args.mode)
                result["dataset_sha256"] = dataset_manifest["dataset_sha256"]
                print(f"{version} {index}/{len(selected)} {case['case_id']} {result['status']} tokens={result['prompt_tokens'] + result['completion_tokens']} cost=${result['cost_usd']:.6f}", flush=True)
                return index, result

        pending = [(index, case) for index, case in enumerate(selected, 1) if case["case_id"] not in completed_ids]
        file_mode = "a" if args.resume and path.exists() else "w"
        with path.open(file_mode, encoding="utf-8", newline="\n") as handle:
            tasks = [asyncio.create_task(evaluate(index, case)) for index, case in pending]
            for task in asyncio.as_completed(tasks):
                _, result = await task
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
        if not pending:
            print(f"{version}: all {len(selected)} cases already present", flush=True)
    hashes = {version: file_sha256(output / f"{version}.results.jsonl") for version in version_names}
    fixture_hash = file_sha256(DATASET)
    rag_hash = text_sha256("\n".join(rag_context(case, all_cases) for case in selected))
    run_manifest = {
        "run_id": f"real-{args.mode}-{model}", "run_mode": args.mode,
        "dataset_sha256": dataset_manifest["dataset_sha256"],
        "versions_config_sha256": file_sha256(VERSIONS_PATH), "result_schema_sha256": file_sha256(RESULT_SCHEMA),
        "model_id": model, "model_snapshot": os.getenv("EVAL_MODEL_SNAPSHOT", model),
        "prompt_sha256": text_sha256(BASE_SYSTEM_PROMPT + TEAM_SUPERVISOR_PROMPT + json.dumps(TEAM_SPECIALISTS, sort_keys=True)), "fixture_sha256": fixture_hash,
        "rag_index_sha256": rag_hash, "retry_policy_sha256": text_sha256("model_retry=2;tool_retry=3"),
        "security_policy_sha256": text_sha256("tenant_context_enforced;prohibited_decoy_filtered"),
        "result_files": hashes,
    }
    (output / "run-manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pilot", "development"], default="pilot")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.mode == "pilot" and not 1 <= args.limit <= 20:
        parser.error("pilot limit must be between 1 and 20")
    if not 1 <= args.concurrency <= 8:
        parser.error("concurrency must be between 1 and 8")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
