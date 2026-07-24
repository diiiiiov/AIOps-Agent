"""Detect exact and high-similarity scenario-family duplicates deterministically."""

from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
JSON_REPORT = ROOT / "evaluation" / "data" / "duplicate-report.v1.json"
MD_REPORT = ROOT / "evaluation" / "data" / "duplicate-report.v1.md"
THRESHOLD = 0.92


def ngrams(value: str, size: int = 3) -> set[str]:
    normalized = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "", value.lower())
    return {normalized[i:i + size] for i in range(max(1, len(normalized) - size + 1))}


def similarity(left: str, right: str) -> float:
    a, b = ngrams(left), ngrams(right)
    return len(a & b) / len(a | b) if a or b else 1.0


def semantic_signature(case: dict) -> str:
    aliases = sorted(alias for root in case["oracle"]["root_causes"] for alias in root["aliases"])
    return "|".join([case["labels"]["category"], case["incident"]["service_name"], *aliases])


def main() -> None:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
    family_cases: dict[str, list[dict]] = {}
    for case in cases:
        family_cases.setdefault(case["labels"]["scenario_family_id"], []).append(case)
    representatives = {family: semantic_signature(values[0]) for family, values in family_cases.items()}
    exact = Counter(representatives.values())
    exact_duplicate_signatures = {key: value for key, value in exact.items() if value > 1}
    near_pairs = []
    families_by_category: dict[str, list[str]] = {}
    for family, values in family_cases.items():
        families_by_category.setdefault(values[0]["labels"]["category"], []).append(family)
    for category, families in families_by_category.items():
        for left, right in combinations(sorted(families), 2):
            score = similarity(representatives[left], representatives[right])
            if score >= THRESHOLD:
                near_pairs.append({"category": category, "left": left, "right": right, "score": round(score, 4)})
    report = {
        "detector": "character-3gram-jaccard",
        "threshold": THRESHOLD,
        "case_count": len(cases),
        "scenario_family_count": len(family_cases),
        "largest_family": max(map(len, family_cases.values())),
        "exact_cross_family_duplicates": exact_duplicate_signatures,
        "near_duplicate_pairs": near_pairs,
        "status": "pass" if not exact_duplicate_signatures and len(family_cases) >= 250 else "fail",
        "limitation": "Deterministic lexical-semantic prefilter; embedding-based and human review are still required before approval."
    }
    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_REPORT.write_text(
        "# Near-duplicate analysis (draft v1)\n\n"
        f"- Detector: character 3-gram Jaccard\n- Threshold: {THRESHOLD}\n"
        f"- Scenario families: {len(family_cases)}\n- Largest family: {report['largest_family']}\n"
        f"- Exact cross-family duplicates: {len(exact_duplicate_signatures)}\n"
        f"- Near-duplicate family pairs: {len(near_pairs)}\n- Gate: **{report['status'].upper()}**\n\n"
        "This is a deterministic prefilter, not a substitute for embedding-based clustering and human review.\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("scenario_family_count", "largest_family", "near_duplicate_pairs", "status")}, default=len, ensure_ascii=False, indent=2))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
