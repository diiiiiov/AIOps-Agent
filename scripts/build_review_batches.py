"""Create deterministic, balanced review batches without approving any case."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "data" / "cases.v1.jsonl"
MANIFEST = ROOT / "evaluation" / "data" / "manifest.v1.json"
OUTPUT = ROOT / "evaluation" / "reviews" / "assignments.v1.json"
SEED = 20260724


def main() -> None:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    buckets: dict[str, list[dict]] = {}
    for case in cases:
        buckets.setdefault(case["labels"]["category"], []).append(case)
    for values in buckets.values():
        rng.shuffle(values)

    batches = [{"batch_id": f"BATCH-{i:02d}", "case_ids": []} for i in range(1, 21)]
    cursor = 0
    for category in sorted(buckets):
        for case in buckets[category]:
            batches[cursor % len(batches)]["case_ids"].append(case["case_id"])
            cursor += 1
    for batch in batches:
        rng.shuffle(batch["case_ids"])
        batch["reviewer_slots"] = ["reviewer_primary", "reviewer_secondary"]
        batch["case_count"] = len(batch["case_ids"])

    counts = Counter(len(batch["case_ids"]) for batch in batches)
    if counts != Counter({50: 20}):
        raise RuntimeError(f"review batches are not balanced: {counts}")
    output = {
        "dataset_sha256": manifest["dataset_sha256"],
        "assignment_version": "1.0.0-draft",
        "seed": SEED,
        "review_policy": "two-independent-reviewers",
        "batches": batches,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"created {len(batches)} review batches with 50 cases each")


if __name__ == "__main__":
    main()
