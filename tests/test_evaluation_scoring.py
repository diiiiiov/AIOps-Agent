import json
import hashlib
from pathlib import Path

import pytest

from evaluation.scoring import (
    cluster_bootstrap_difference,
    mcnemar_exact,
    score_case,
    validate_result,
)
from scripts.generate_smoke_replay import make_result


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _first_case():
    line = (ROOT / "evaluation" / "data" / "cases.v1.jsonl").read_text(encoding="utf-8").splitlines()[0]
    return json.loads(line)


def test_v3_oracle_replay_scores_perfectly():
    case = _first_case()
    manifest = _load(ROOT / "evaluation" / "data" / "manifest.v1.json")
    versions = _load(ROOT / "evaluation" / "config" / "versions.json")
    schema = _load(ROOT / "evaluation" / "schema" / "result.schema.json")
    result = make_result(case, "V3", versions["versions"]["V3"], manifest["dataset_sha256"])
    validate_result(result, case, dataset_sha256=manifest["dataset_sha256"], schema=schema, versions=versions)
    score = score_case(case, result)
    assert score["root_f1"] == 1
    assert score["tool_f1"] == 1
    assert score["evidence_f1"] == 1
    assert score["cross_tenant_leak"] == 0


def test_v4_scores_team_collaboration():
    case = _first_case()
    manifest = _load(ROOT / "evaluation" / "data" / "manifest.v1.json")
    versions = _load(ROOT / "evaluation" / "config" / "versions.json")
    schema = _load(ROOT / "evaluation" / "schema" / "result.schema.json")
    result = make_result(case, "V4", versions["versions"]["V4"], manifest["dataset_sha256"])
    validate_result(result, case, dataset_sha256=manifest["dataset_sha256"], schema=schema, versions=versions)
    score = score_case(case, result)
    assert score["specialist_success_rate"] == 1
    assert score["cross_validation_completed"] == 1
    assert score["parallel_speedup"] >= 1


def test_version_boundary_rejects_mcp_calls_in_v0():
    case = _first_case()
    manifest = _load(ROOT / "evaluation" / "data" / "manifest.v1.json")
    versions = _load(ROOT / "evaluation" / "config" / "versions.json")
    schema = _load(ROOT / "evaluation" / "schema" / "result.schema.json")
    result = make_result(case, "V0", versions["versions"]["V0"], manifest["dataset_sha256"])
    result["tool_calls"] = [{"tool_name": "search_log", "tenant_id": "tenant-00", "attempts": 1, "success": True, "approved": True}]
    with pytest.raises(ValueError, match="cannot call MCP tools"):
        validate_result(result, case, dataset_sha256=manifest["dataset_sha256"], schema=schema, versions=versions)


def test_cluster_bootstrap_and_mcnemar_are_deterministic():
    left = {
        "A": {"scenario_family_id": "F1", "task_completed": 0.0},
        "B": {"scenario_family_id": "F1", "task_completed": 0.0},
        "C": {"scenario_family_id": "F2", "task_completed": 1.0},
    }
    right = {
        "A": {"scenario_family_id": "F1", "task_completed": 1.0},
        "B": {"scenario_family_id": "F1", "task_completed": 1.0},
        "C": {"scenario_family_id": "F2", "task_completed": 1.0},
    }
    comparison = cluster_bootstrap_difference(left, right, "task_completed", iterations=100, seed=7)
    assert comparison["difference"] == pytest.approx(2 / 3)
    assert comparison["ci95_low"] <= comparison["difference"] <= comparison["ci95_high"]
    test = mcnemar_exact(left, right, "task_completed")
    assert test == {"left_only": 0, "right_only": 2, "p_value": 0.5}


def test_smoke_run_manifest_binds_all_result_files():
    directory = ROOT / "evaluation" / "results" / "smoke"
    run_manifest = _load(directory / "run-manifest.json")
    manifest = _load(ROOT / "evaluation" / "data" / "manifest.v1.json")
    assert run_manifest["run_mode"] == "smoke_replay"
    assert run_manifest["dataset_sha256"] == manifest["dataset_sha256"]
    for version in ("V0", "V1", "V2", "V3", "V4"):
        path = directory / f"{version}.results.jsonl"
        assert run_manifest["result_files"][version] == hashlib.sha256(path.read_bytes()).hexdigest()
