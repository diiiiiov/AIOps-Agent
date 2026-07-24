"""Record independent reviews, arbitrate disagreements, and summarize coverage."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
REVIEW_SCHEMA = ROOT / "evaluation" / "schema" / "review.schema.json"
ARBITRATION_SCHEMA = ROOT / "evaluation" / "schema" / "arbitration.schema.json"
RECORDS = ROOT / "evaluation" / "reviews" / "records"
SUMMARY = ROOT / "evaluation" / "reviews" / "summary.v1.json"
CHECKS = [
    "incident_is_coherent", "evidence_is_consistent", "root_causes_are_correct",
    "root_causes_are_complete", "tool_oracle_is_correct", "action_oracle_is_correct",
    "tenant_risk_is_correct", "difficulty_is_correct",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,64}", value):
        raise ValueError("reviewer id must contain only letters, digits, dot, dash or underscore")
    return value


def validate(record: dict, schema_path: Path) -> None:
    errors = list(Draft202012Validator(load(schema_path), format_checker=FormatChecker()).iter_errors(record))
    if errors:
        raise ValueError("; ".join(error.message for error in errors))


def context() -> tuple[dict, set[str], Path]:
    manifest = load(MANIFEST)
    case_ids = {json.loads(line)["case_id"] for line in DATASET.read_text(encoding="utf-8").splitlines() if line}
    directory = RECORDS / manifest["dataset_sha256"][:12]
    directory.mkdir(parents=True, exist_ok=True)
    return manifest, case_ids, directory


def record_review(args: argparse.Namespace) -> None:
    manifest, case_ids, directory = context()
    if args.case_id not in case_ids:
        raise ValueError("unknown case id")
    reviewer = safe_id(args.reviewer_id)
    checks = {name: name not in set(args.fail_check or []) for name in CHECKS}
    if args.decision == "approve" and (not all(checks.values()) or args.realism_score < 4):
        raise ValueError("approve requires all checks to pass and realism_score >= 4")
    record = {
        "case_id": args.case_id,
        "dataset_sha256": manifest["dataset_sha256"],
        "reviewer_id": reviewer,
        "independent_review": True,
        "decision": args.decision,
        "checks": checks,
        "realism_score": args.realism_score,
        "notes": args.notes,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    validate(record, REVIEW_SCHEMA)
    path = directory / f"{args.case_id}.{reviewer}.review.json"
    if path.exists() and not args.replace:
        raise FileExistsError(f"review already exists: {path}")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


def arbitrate(args: argparse.Namespace) -> None:
    manifest, case_ids, directory = context()
    if args.case_id not in case_ids:
        raise ValueError("unknown case id")
    reviews = [load(path) for path in directory.glob(f"{args.case_id}.*.review.json")]
    reviewer_ids = sorted({record["reviewer_id"] for record in reviews})
    arbitrator = safe_id(args.arbitrator_id)
    if len(reviewer_ids) < 2:
        raise ValueError("arbitration requires two independent reviews")
    if arbitrator in reviewer_ids:
        raise ValueError("arbitrator must differ from both reviewers")
    record = {
        "case_id": args.case_id,
        "dataset_sha256": manifest["dataset_sha256"],
        "arbitrator_id": arbitrator,
        "reviewer_ids": reviewer_ids[:2],
        "decision": args.decision,
        "rationale": args.rationale,
        "arbitrated_at": datetime.now(timezone.utc).isoformat(),
    }
    validate(record, ARBITRATION_SCHEMA)
    path = directory / f"{args.case_id}.{arbitrator}.arbitration.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


def summarize(_: argparse.Namespace) -> None:
    manifest, case_ids, directory = context()
    reviews: dict[str, list[dict]] = defaultdict(list)
    arbitrations: dict[str, dict] = {}
    for path in directory.glob("*.review.json"):
        record = load(path); validate(record, REVIEW_SCHEMA); reviews[record["case_id"]].append(record)
    for path in directory.glob("*.arbitration.json"):
        record = load(path); validate(record, ARBITRATION_SCHEMA); arbitrations[record["case_id"]] = record
    statuses = {}
    for case_id in sorted(case_ids):
        unique = {record["reviewer_id"]: record for record in reviews[case_id]}
        decisions = [record["decision"] for record in unique.values()]
        if case_id in arbitrations:
            status = arbitrations[case_id]["decision"]
        elif len(unique) < 2:
            status = "pending"
        elif decisions.count("approve") >= 2:
            status = "approve"
        elif len(set(decisions)) > 1:
            status = "needs_arbitration"
        else:
            status = decisions[0]
        statuses[case_id] = status
    counts: dict[str, int] = defaultdict(int)
    for value in statuses.values(): counts[value] += 1
    result = {"dataset_sha256": manifest["dataset_sha256"], "counts": dict(counts), "statuses": statuses}
    SUMMARY.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    review = commands.add_parser("record")
    review.add_argument("--case-id", required=True); review.add_argument("--reviewer-id", required=True)
    review.add_argument("--decision", choices=["approve", "revise", "reject"], required=True)
    review.add_argument("--realism-score", type=int, choices=range(1, 6), required=True)
    review.add_argument("--fail-check", action="append", choices=CHECKS)
    review.add_argument("--notes", default=""); review.add_argument("--replace", action="store_true")
    review.set_defaults(func=record_review)
    arbitration = commands.add_parser("arbitrate")
    arbitration.add_argument("--case-id", required=True); arbitration.add_argument("--arbitrator-id", required=True)
    arbitration.add_argument("--decision", choices=["approve", "revise", "reject"], required=True)
    arbitration.add_argument("--rationale", required=True); arbitration.set_defaults(func=arbitrate)
    summary = commands.add_parser("summary"); summary.set_defaults(func=summarize)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
