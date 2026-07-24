# REAL MODEL DEVELOPMENT EVALUATION

Dataset SHA-256: `3b05177b805bc0a8d4200e3adeabfb0c5eed4c320488ef646857877e77fb3768`

## Overall

| Version | Completion | Root F1 | Tool F1 | Evidence F1 | Action F1 | Leak rate | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1.000 | 0.141 | 0.000 | 0.000 | 0.542 | 0.000 | 1651.0 |
| V1 | 1.000 | 0.163 | 0.000 | 0.000 | 0.552 | 0.000 | 1109.7 |
| V2 | 1.000 | 0.448 | 0.400 | 0.247 | 0.689 | 0.000 | 2799.3 |
| V3 | 1.000 | 0.973 | 0.572 | 0.707 | 0.983 | 0.000 | 7731.4 |

## Adjacent-version cluster-bootstrap differences

| Comparison | Metric | Difference | 95% CI |
|---|---|---:|---:|
| V0_vs_V1 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | root_f1 | 0.0217 | [-0.0017, 0.0481] |
| V0_vs_V1 | root_exact_match | 0.0150 | [0.0000, 0.0352] |
| V0_vs_V1 | tool_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | evidence_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | action_f1 | 0.0095 | [-0.0040, 0.0244] |
| V0_vs_V1 | hallucination_rate | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | root_f1 | 0.2858 | [0.2151, 0.3550] |
| V1_vs_V2 | root_exact_match | 0.3050 | [0.2335, 0.3769] |
| V1_vs_V2 | tool_f1 | 0.4002 | [0.3821, 0.4182] |
| V1_vs_V2 | evidence_f1 | 0.2470 | [0.1970, 0.2975] |
| V1_vs_V2 | action_f1 | 0.1367 | [0.0949, 0.1782] |
| V1_vs_V2 | hallucination_rate | -0.6900 | [-0.7239, -0.6559] |
| V1_vs_V2 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | task_completed | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | root_f1 | 0.5243 | [0.4569, 0.5904] |
| V2_vs_V3 | root_exact_match | 0.5050 | [0.4278, 0.5813] |
| V2_vs_V3 | tool_f1 | 0.1718 | [0.1526, 0.1908] |
| V2_vs_V3 | evidence_f1 | 0.4602 | [0.4096, 0.5095] |
| V2_vs_V3 | action_f1 | 0.2946 | [0.2530, 0.3369] |
| V2_vs_V3 | hallucination_rate | -0.2954 | [-0.3296, -0.2631] |
| V2_vs_V3 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | policy_violation | 0.0000 | [0.0000, 0.0000] |
