"""Validate, score and compare configured evaluation versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.scoring import (
    PRIMARY_METRICS,
    aggregate,
    compare_versions,
    read_jsonl,
    score_case,
    sliced_aggregates,
    validate_result,
)
from jsonschema import Draft202012Validator


DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
SCHEMA = ROOT / "evaluation" / "schema" / "result.schema.json"
VERSIONS = ROOT / "evaluation" / "config" / "versions.json"
RUN_MANIFEST_SCHEMA = ROOT / "evaluation" / "schema" / "run-manifest.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=ROOT / "evaluation" / "results" / "smoke")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = {item["case_id"]: item for item in read_jsonl(DATASET)}
    manifest, schema, versions = load(MANIFEST), load(SCHEMA), load(VERSIONS)
    version_names = list(versions["versions"])
    run_manifest = load(args.results_dir / "run-manifest.json")
    manifest_errors = list(Draft202012Validator(load(RUN_MANIFEST_SCHEMA)).iter_errors(run_manifest))
    if manifest_errors:
        raise ValueError(f"run manifest is invalid: {manifest_errors[0].message}")
    if run_manifest["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("run manifest is bound to a different dataset")
    if run_manifest["versions_config_sha256"] != file_sha256(VERSIONS):
        raise ValueError("version capability configuration changed after the run")
    if run_manifest["result_schema_sha256"] != file_sha256(SCHEMA):
        raise ValueError("result schema changed after the run")
    scores_by_version: dict[str, list[dict]] = {}
    run_modes: set[str] = set()
    for version in version_names:
        path = args.results_dir / f"{version}.results.jsonl"
        if run_manifest["result_files"][version] != file_sha256(path):
            raise ValueError(f"result file hash mismatch: {path}")
        results = read_jsonl(path)
        if len({item["case_id"] for item in results}) != len(results):
            raise ValueError(f"duplicate case result in {path}")
        result_ids = {item["case_id"] for item in results}
        if not result_ids.issubset(cases):
            raise ValueError(f"unknown case result in {path}")
        for result in results:
            if result["version"] != version:
                raise ValueError(f"wrong version in {path}")
            case = cases[result["case_id"]]
            validate_result(result, case, dataset_sha256=manifest["dataset_sha256"], schema=schema, versions=versions)
            run_modes.add(result["run_mode"])
        scores_by_version[version] = [score_case(cases[item["case_id"]], item) for item in results]

    if len(run_modes) != 1:
        raise ValueError("run modes cannot be mixed")
    run_mode = next(iter(run_modes))
    if run_manifest["run_mode"] != run_mode:
        raise ValueError("run manifest mode does not match result records")
    if run_mode == "formal":
        for version, scores in scores_by_version.items():
            selected = {item["case_id"] for item in scores}
            invalid = [cases[case_id] for case_id in selected if cases[case_id]["split"] != "sealed_test" or cases[case_id]["review_status"] != "approved"]
            if invalid:
                raise ValueError(f"formal {version} includes unapproved or non-sealed cases")
    elif run_mode == "development":
        expected = {case_id for case_id, case in cases.items() if case["split"] == "development"}
        for version, scores in scores_by_version.items():
            if {item["case_id"] for item in scores} != expected:
                raise ValueError(f"development run {version} must cover all 200 development cases")
    elif run_mode == "pilot":
        selected_sets = [{item["case_id"] for item in scores} for scores in scores_by_version.values()]
        if not selected_sets[0] or any(selected != selected_sets[0] for selected in selected_sets[1:]):
            raise ValueError("pilot versions must cover the same non-empty case subset")
        if any(cases[case_id]["split"] != "development" for case_id in selected_sets[0]):
            raise ValueError("pilot can only use development cases")
    else:
        expected = set(cases)
        for version, scores in scores_by_version.items():
            if {item["case_id"] for item in scores} != expected:
                raise ValueError(f"smoke replay {version} must cover all 1000 cases")

    report = {
        "report_type": (
            "SMOKE PIPELINE TEST - NOT MODEL EVALUATION" if run_mode == "smoke_replay"
            else "REAL MODEL DEVELOPMENT PILOT - PRELIMINARY" if run_mode == "pilot"
            else "REAL MODEL DEVELOPMENT EVALUATION" if run_mode == "development"
            else "FORMAL EVALUATION"
        ),
        "run_mode": run_mode,
        "dataset_sha256": manifest["dataset_sha256"],
        "run_id": run_manifest["run_id"],
        "fixed_conditions": {
            key: run_manifest[key] for key in (
                "model_id", "model_snapshot", "prompt_sha256", "fixture_sha256",
                "rag_index_sha256", "retry_policy_sha256", "security_policy_sha256",
            )
        },
        "versions": {
            version: {"overall": aggregate(scores), "slices": sliced_aggregates(scores)}
            for version, scores in scores_by_version.items()
        },
        "comparisons": compare_versions(scores_by_version),
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output_dir / "case-scores.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for version in version_names:
            for score in scores_by_version[version]:
                handle.write(json.dumps(score, ensure_ascii=False, sort_keys=True) + "\n")
    write_markdown(output_dir / "report.md", report)
    print(output_dir / "report.md")


def write_markdown(path: Path, report: dict) -> None:
    rows = [
        f"# {report['report_type']}", "",
        f"Dataset SHA-256: `{report['dataset_sha256']}`", "",
    ]
    if report["run_mode"] == "smoke_replay":
        rows.extend(["> **WARNING:** Oracle-derived synthetic replay. These numbers do not measure any model or Agent version.", ""])
    elif report["run_mode"] == "pilot":
        rows.extend(["> **WARNING:** Small development pilot. Do not report these preliminary numbers as formal results.", ""])
    rows.extend(["## Overall", "", "| Version | Completion | Root F1 | Tool F1 | Evidence F1 | Action F1 | Leak rate | P95 latency (ms) |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for version in report["versions"]:
        metrics = report["versions"][version]["overall"]["metrics"]
        rows.append(
            f"| {version} | {metrics['task_completed']:.3f} | {metrics['root_f1']:.3f} | "
            f"{metrics['tool_f1']:.3f} | {metrics['evidence_f1']:.3f} | {metrics['action_f1']:.3f} | "
            f"{metrics['cross_tenant_leak']:.3f} | {metrics['latency_p95_ms']:.1f} |"
        )
    rows.extend([
        "", "## Collaboration (V4 Team)", "",
        "| Version | Specialist success | Specialist evidence recall | Cross-validation | Parallel speedup |",
        "|---|---:|---:|---:|---:|",
    ])
    for version in report["versions"]:
        metrics = report["versions"][version]["overall"]["metrics"]
        rows.append(
            f"| {version} | {metrics['specialist_success_rate']:.3f} | "
            f"{metrics['specialist_evidence_recall']:.3f} | "
            f"{metrics['cross_validation_completed']:.3f} | {metrics['parallel_speedup']:.2f}x |"
        )
    rows.extend(["", "## Adjacent-version cluster-bootstrap differences", "", "| Comparison | Metric | Difference | 95% CI |", "|---|---|---:|---:|"])
    for label, comparison in report["comparisons"].items():
        for metric in PRIMARY_METRICS:
            value = comparison["metrics"][metric]
            rows.append(f"| {label} | {metric} | {value['difference']:.4f} | [{value['ci95_low']:.4f}, {value['ci95_high']:.4f}] |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
