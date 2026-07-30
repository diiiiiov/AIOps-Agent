# Evaluation execution and scoring

## Smoke pipeline test

The smoke replay validates the complete result-processing pipeline without
calling an LLM:

```powershell
python scripts/generate_smoke_replay.py
python scripts/score_evaluation_results.py
```

The generated report is prominently marked `NOT MODEL EVALUATION`. Its values
are oracle-derived synthetic fixtures and must never appear as project results.

## Formal result contract

A formal adapter must write five files named `V0.results.jsonl` through
`V4.results.jsonl`, each conforming to `evaluation/schema/result.schema.json`.
The directory must also contain `run-manifest.json` conforming to
`evaluation/schema/run-manifest.schema.json`.

The single run manifest freezes conditions shared by all versions:

- dataset SHA-256;
- version configuration and result Schema hashes;
- exact model identifier and snapshot;
- system prompt, MCP fixture and RAG index hashes;
- retry and security policy hashes;
- hashes of all five result files.

The scorer rejects capability-boundary violations, stale datasets, modified
result files, mixed run modes, duplicate cases, or formal runs containing any
non-approved/development sample.

## Statistical output

```powershell
python scripts/score_evaluation_results.py `
  --results-dir evaluation/results/<formal-run-id>
```

The scorer emits per-case scores, overall and sliced aggregates, adjacent-version
paired comparisons, scenario-family cluster-bootstrap 95% confidence intervals,
exact McNemar tests for binary metrics, and Holm-adjusted p-values.

The repository currently provides the result contract, scorer and smoke adapter.
A real V0-V4 model adapter must not be enabled until the sealed test set has been
independently reviewed and approved.
