# REAL MODEL DEVELOPMENT PILOT - PRELIMINARY

Dataset SHA-256: `3b05177b805bc0a8d4200e3adeabfb0c5eed4c320488ef646857877e77fb3768`

> **WARNING:** Small development pilot. Do not report these preliminary numbers as formal results.

## Overall

| Version | Completion | Root F1 | Tool F1 | Evidence F1 | Action F1 | Leak rate | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1.000 | 0.000 | 0.000 | 0.000 | 0.467 | 0.000 | 2117.2 |
| V1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.467 | 0.000 | 1025.4 |
| V2 | 0.667 | 0.333 | 0.267 | 0.222 | 0.633 | 0.000 | 2529.0 |
| V3 | 0.000 | 1.000 | 0.489 | 0.711 | 1.000 | 0.000 | 5892.6 |

## Adjacent-version cluster-bootstrap differences

| Comparison | Metric | Difference | 95% CI |
|---|---|---:|---:|
| V0_vs_V1 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | root_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | root_exact_match | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | tool_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | evidence_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | action_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | hallucination_rate | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | task_completed | -0.3333 | [-1.0000, 0.0000] |
| V1_vs_V2 | root_f1 | 0.3333 | [0.0000, 1.0000] |
| V1_vs_V2 | root_exact_match | 0.3333 | [0.0000, 1.0000] |
| V1_vs_V2 | tool_f1 | 0.2667 | [0.0000, 0.4000] |
| V1_vs_V2 | evidence_f1 | 0.2222 | [0.0000, 0.6667] |
| V1_vs_V2 | action_f1 | 0.1667 | [0.0000, 0.5000] |
| V1_vs_V2 | hallucination_rate | -0.6667 | [-1.0000, -0.5000] |
| V1_vs_V2 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | task_completed | -0.6667 | [-1.0000, 0.0000] |
| V2_vs_V3 | root_f1 | 0.6667 | [0.0000, 1.0000] |
| V2_vs_V3 | root_exact_match | 0.6667 | [0.0000, 1.0000] |
| V2_vs_V3 | tool_f1 | 0.2222 | [0.0000, 0.4000] |
| V2_vs_V3 | evidence_f1 | 0.4889 | [0.0000, 0.8000] |
| V2_vs_V3 | action_f1 | 0.3667 | [0.0000, 0.6000] |
| V2_vs_V3 | hallucination_rate | -0.3333 | [-0.5000, 0.0000] |
| V2_vs_V3 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | policy_violation | 0.0000 | [0.0000, 0.0000] |
