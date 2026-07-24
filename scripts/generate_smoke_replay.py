"""Generate oracle-derived synthetic traces to test the evaluator, never model quality."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
VERSIONS = ROOT / "evaluation" / "config" / "versions.json"
OUTPUT = ROOT / "evaluation" / "results" / "smoke"
RESULT_SCHEMA = ROOT / "evaluation" / "schema" / "result.schema.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = json.loads(VERSIONS.read_text(encoding="utf-8"))["versions"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for version, config in versions.items():
        path = OUTPUT / f"{version}.results.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for case in cases:
                handle.write(json.dumps(make_result(case, version, config, manifest["dataset_sha256"]), ensure_ascii=False) + "\n")
        print(path)
    run_manifest = {
        "run_id": "smoke-oracle-replay-v1",
        "run_mode": "smoke_replay",
        "dataset_sha256": manifest["dataset_sha256"],
        "versions_config_sha256": file_sha256(VERSIONS),
        "result_schema_sha256": file_sha256(RESULT_SCHEMA),
        "model_id": "SMOKE_ORACLE_REPLAY",
        "model_snapshot": "not-a-model",
        "prompt_sha256": text_sha256("smoke-prompt"),
        "fixture_sha256": text_sha256("smoke-fixture"),
        "rag_index_sha256": text_sha256("smoke-rag-index"),
        "retry_policy_sha256": text_sha256("smoke-retry-policy"),
        "security_policy_sha256": text_sha256("smoke-security-policy"),
        "result_files": {
            version: file_sha256(OUTPUT / f"{version}.results.jsonl") for version in versions
        },
    }
    (OUTPUT / "run-manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def make_result(case: dict, version: str, config: dict, dataset_sha256: str) -> dict:
    serial = int(case["case_id"].split("-")[1])
    roots = [item["root_cause_id"] for item in case["oracle"]["root_causes"]]
    evidence = list(case["oracle"]["required_evidence_ids"])
    actions = list(case["oracle"]["recommended_action_ids"])
    if version == "V0":
        predicted_roots = roots[:1] if serial % 5 else []
        predicted_evidence, predicted_actions, tools = [], actions[:1], []
        failed = serial % 20 == 0
    elif version == "V1":
        predicted_roots = roots[:1] if serial % 10 else []
        predicted_evidence, predicted_actions, tools = evidence[:1], actions[:1], []
        failed = serial % 50 == 0
    else:
        predicted_roots = roots[:1] if version == "V2" and serial % 8 == 0 else roots
        predicted_evidence = evidence
        predicted_actions = actions
        tools = []
        for name in case["oracle"]["required_tools"]:
            injected = any(item["tool"] == name for item in case["constraints"]["injected_failures"])
            attempts = 2 if injected and (version == "V3" or serial % 7) else 1
            tools.append({
                "tool_name": name,
                "tenant_id": case["tenant_context"]["request_tenant_id"],
                "attempts": attempts,
                "success": True,
                "approved": True,
            })
        failed = version == "V2" and serial % 100 == 0
    factor = {"V0": 1.0, "V1": 1.25, "V2": 1.7, "V3": 2.0}[version]
    return {
        "case_id": case["case_id"],
        "dataset_sha256": dataset_sha256,
        "version": version,
        "run_mode": "smoke_replay",
        "capabilities": {key: config[key] for key in ("rag_enabled", "mcp_enabled", "replan_enabled")},
        "status": "failed" if failed else "completed",
        "root_cause_ids": predicted_roots,
        "evidence_ids": predicted_evidence,
        "tool_calls": tools,
        "action_ids": predicted_actions,
        "policy_violations": [],
        "latency_ms": round((80 + serial % 37) * factor, 3),
        "prompt_tokens": int((450 + serial % 120) * factor),
        "completion_tokens": int((120 + serial % 50) * factor),
        "cost_usd": round((0.0002 + (serial % 30) / 100000) * factor, 7),
        "steps": {"V0": 2, "V1": 2, "V2": 4, "V3": 5}[version],
        "error": "synthetic_failure" if failed else None,
    }


if __name__ == "__main__":
    main()
