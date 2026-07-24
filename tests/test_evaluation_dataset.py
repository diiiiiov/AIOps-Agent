from pathlib import Path
import json

from scripts.build_evaluation_dataset import (
    PLAN_PATH,
    SCHEMA_PATH,
    build_cases,
    load_json,
    validate_cases,
)


def test_generated_dataset_matches_frozen_quotas():
    plan, schema = load_json(PLAN_PATH), load_json(SCHEMA_PATH)
    cases = build_cases(plan)
    counts = validate_cases(cases, plan, schema)
    assert counts["total"] == 1000
    assert counts["cross_tenant_risk"] == {"false": 750, "true": 250}
    assert counts["root_cause_mode"] == {"single": 700, "multiple": 300}
    assert counts["split_cross_tenant"] == {"development": 50, "sealed_test": 200}
    assert counts["diversity"]["unique_prompts"] == 1000
    assert counts["diversity"]["unique_services"] == 50
    assert counts["diversity"]["scenario_families"] == 250
    assert counts["diversity"]["largest_family"] <= 6


def test_cross_tenant_decoys_never_enter_gold_evidence():
    cases = build_cases(load_json(PLAN_PATH))
    for case in cases:
        prohibited = {
            item["evidence_id"]
            for item in case["observations"]
            if item["access_scope"] == "prohibited_decoy"
        }
        assert prohibited.isdisjoint(case["oracle"]["required_evidence_ids"])


def test_difficulty_labels_have_objective_case_features():
    cases = build_cases(load_json(PLAN_PATH))
    for case in cases:
        evidence = {item["evidence_id"] for item in case["observations"]}
        difficulty = case["labels"]["difficulty"]
        if difficulty == "easy":
            assert case["labels"]["root_cause_mode"] == "single"
            assert not case["constraints"]["injected_failures"]
        elif difficulty == "medium":
            assert "E90" in evidence
        else:
            assert {"E90", "E91"}.issubset(evidence)
            assert case["constraints"]["injected_failures"]


def test_review_batches_cover_every_case_once_with_two_slots():
    root = Path(__file__).resolve().parents[1]
    assignments = json.loads(
        (root / "evaluation" / "reviews" / "assignments.v1.json").read_text(encoding="utf-8")
    )
    case_ids = [case_id for batch in assignments["batches"] for case_id in batch["case_ids"]]
    assert len(assignments["batches"]) == 20
    assert all(batch["case_count"] == 50 for batch in assignments["batches"])
    assert all(len(batch["reviewer_slots"]) == 2 for batch in assignments["batches"])
    assert len(case_ids) == len(set(case_ids)) == 1000


def test_duplicate_gate_and_artifacts_bind_to_current_dataset():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "evaluation" / "data" / "manifest.v1.json").read_text(encoding="utf-8")
    )
    duplicate_report = json.loads(
        (root / "evaluation" / "data" / "duplicate-report.v1.json").read_text(encoding="utf-8")
    )
    assignments = json.loads(
        (root / "evaluation" / "reviews" / "assignments.v1.json").read_text(encoding="utf-8")
    )
    assert duplicate_report["status"] == "pass"
    assert duplicate_report["scenario_family_count"] == 250
    assert not duplicate_report["exact_cross_family_duplicates"]
    assert assignments["dataset_sha256"] == manifest["dataset_sha256"]
