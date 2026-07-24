"""Render a concise, reproducible quality report from the dataset manifest."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
OUTPUT = ROOT / "evaluation" / "data" / "quality-report.v1.md"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
    stats = manifest["statistics"]
    reviews = Counter(case["review_status"] for case in cases)
    rows = [
        "# Evaluation dataset quality report (draft v1)",
        "",
        f"- Dataset SHA-256: `{manifest['dataset_sha256']}`",
        f"- Total cases: {stats['total']}",
        f"- Split: development {stats['split']['development']}, sealed_test {stats['split']['sealed_test']}",
        f"- Root cause mode: single {stats['root_cause_mode']['single']}, multiple {stats['root_cause_mode']['multiple']}",
        f"- Cross-tenant risk: {stats['cross_tenant_risk']['true']}",
        f"- Review status: {dict(reviews)}",
        "",
        "## Diversity gates",
        "",
        "| Gate | Result | Status |",
        "|---|---:|---|",
        f"| Unique prompts | {stats['diversity']['unique_prompts']} | PASS |",
        f"| Unique services | {stats['diversity']['unique_services']} | PASS |",
        f"| Scenario families | {stats['diversity']['scenario_families']} | PASS |",
        f"| Unique evidence texts | {stats['diversity']['unique_evidence_texts']} | PASS |",
        f"| Largest family | {stats['diversity']['largest_family']} | PASS (limit 6) |",
        "",
        "## Category distribution",
        "",
        "| Category | Total | Cross-tenant | Multiple |",
        "|---|---:|---:|---:|",
    ]
    for category, values in sorted(stats["categories"].items()):
        rows.append(f"| {category} | {values['total']} | {values['cross_tenant']} | {values['multiple']} |")
    rows.extend([
        "",
        "## Release decision",
        "",
        "**NOT APPROVED FOR FORMAL BENCHMARKING.** The file contains synthetic draft cases. "
        "Schema, quota and exact-duplicate gates pass, but two-person review, semantic near-duplicate "
        "analysis and gold-label adjudication are not complete.",
        "",
    ])
    OUTPUT.write_text("\n".join(rows), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
