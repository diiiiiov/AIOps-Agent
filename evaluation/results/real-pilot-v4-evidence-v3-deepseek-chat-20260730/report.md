# REAL MODEL DEVELOPMENT PILOT - PRELIMINARY

Dataset SHA-256: `3b05177b805bc0a8d4200e3adeabfb0c5eed4c320488ef646857877e77fb3768`

> **WARNING:** Small development pilot. Do not report these preliminary numbers as formal results.

## Overall

| Version | Completion | Root F1 | Tool F1 | Evidence F1 | Action F1 | Leak rate | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1.000 | 0.000 | 0.000 | 0.000 | 0.480 | 0.000 | 1903.2 |
| V1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.480 | 0.000 | 1042.3 |
| V2 | 1.000 | 0.400 | 0.320 | 0.267 | 0.680 | 0.000 | 2555.5 |
| V3 | 1.000 | 0.933 | 0.507 | 0.693 | 0.960 | 0.000 | 7070.4 |
| V4 | 1.000 | 0.933 | 0.540 | 0.933 | 0.960 | 0.000 | 3271.6 |

## Collaboration (V4 Team)

| Version | Specialist success | Specialist evidence recall | Cross-validation | Parallel speedup |
|---|---:|---:|---:|---:|
| V0 | 0.000 | 0.000 | 0.000 | 0.00x |
| V1 | 0.000 | 0.000 | 0.000 | 0.00x |
| V2 | 0.000 | 0.000 | 0.000 | 0.00x |
| V3 | 0.000 | 0.000 | 0.000 | 0.00x |
| V4 | 1.000 | 1.000 | 1.000 | 2.35x |

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
| V0_vs_V1 | specialist_success_rate | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | specialist_evidence_recall | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | cross_validation_completed | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | root_f1 | 0.4000 | [0.0000, 0.8000] |
| V1_vs_V2 | root_exact_match | 0.4000 | [0.0000, 0.8000] |
| V1_vs_V2 | tool_f1 | 0.3200 | [0.1600, 0.4000] |
| V1_vs_V2 | evidence_f1 | 0.2667 | [0.0000, 0.5333] |
| V1_vs_V2 | action_f1 | 0.2000 | [0.0000, 0.4000] |
| V1_vs_V2 | hallucination_rate | -0.7000 | [-0.9000, -0.5000] |
| V1_vs_V2 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | specialist_success_rate | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | specialist_evidence_recall | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | cross_validation_completed | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | root_f1 | 0.5333 | [0.1333, 0.9333] |
| V2_vs_V3 | root_exact_match | 0.4000 | [0.0000, 0.8000] |
| V2_vs_V3 | tool_f1 | 0.1867 | [0.0533, 0.3200] |
| V2_vs_V3 | evidence_f1 | 0.4267 | [0.1333, 0.7200] |
| V2_vs_V3 | action_f1 | 0.2800 | [0.0600, 0.5000] |
| V2_vs_V3 | hallucination_rate | -0.2500 | [-0.4500, -0.0500] |
| V2_vs_V3 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | specialist_success_rate | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | specialist_evidence_recall | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | cross_validation_completed | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | root_f1 | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | root_exact_match | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | tool_f1 | 0.0333 | [-0.1200, 0.1200] |
| V3_vs_V4 | evidence_f1 | 0.2400 | [0.1067, 0.3333] |
| V3_vs_V4 | action_f1 | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | hallucination_rate | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V3_vs_V4 | specialist_success_rate | 1.0000 | [1.0000, 1.0000] |
| V3_vs_V4 | specialist_evidence_recall | 1.0000 | [1.0000, 1.0000] |
| V3_vs_V4 | cross_validation_completed | 1.0000 | [1.0000, 1.0000] |
