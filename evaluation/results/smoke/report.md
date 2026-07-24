# SMOKE PIPELINE TEST - NOT MODEL EVALUATION

Dataset SHA-256: `3b05177b805bc0a8d4200e3adeabfb0c5eed4c320488ef646857877e77fb3768`

> **WARNING:** Oracle-derived synthetic replay. These numbers do not measure any model or Agent version.

## Overall

| Version | Completion | Root F1 | Tool F1 | Evidence F1 | Action F1 | Leak rate | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 0.950 | 0.719 | 0.000 | 0.000 | 0.617 | 0.000 | 115.0 |
| V1 | 0.980 | 0.809 | 0.000 | 0.900 | 0.617 | 0.000 | 143.8 |
| V2 | 0.990 | 0.986 | 1.000 | 1.000 | 1.000 | 0.000 | 195.5 |
| V3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 230.0 |

## Adjacent-version cluster-bootstrap differences

| Comparison | Metric | Difference | 95% CI |
|---|---|---:|---:|
| V0_vs_V1 | task_completed | 0.0300 | [0.0169, 0.0431] |
| V0_vs_V1 | root_f1 | 0.0903 | [0.0741, 0.1068] |
| V0_vs_V1 | root_exact_match | 0.0710 | [0.0553, 0.0867] |
| V0_vs_V1 | tool_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | evidence_f1 | 0.9000 | [0.8908, 0.9085] |
| V0_vs_V1 | action_f1 | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | hallucination_rate | -0.8000 | [-0.8235, -0.7761] |
| V0_vs_V1 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V0_vs_V1 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | task_completed | 0.0100 | [0.0040, 0.0163] |
| V1_vs_V2 | root_f1 | 0.1767 | [0.1595, 0.1949] |
| V1_vs_V2 | root_exact_match | 0.3300 | [0.3029, 0.3581] |
| V1_vs_V2 | tool_f1 | 1.0000 | [1.0000, 1.0000] |
| V1_vs_V2 | evidence_f1 | 0.1000 | [0.0915, 0.1092] |
| V1_vs_V2 | action_f1 | 0.3833 | [0.3791, 0.3880] |
| V1_vs_V2 | hallucination_rate | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V1_vs_V2 | policy_violation | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | task_completed | 0.0100 | [0.0049, 0.0164] |
| V2_vs_V3 | root_f1 | 0.0140 | [0.0102, 0.0180] |
| V2_vs_V3 | root_exact_match | 0.0420 | [0.0306, 0.0541] |
| V2_vs_V3 | tool_f1 | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | evidence_f1 | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | action_f1 | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | hallucination_rate | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | cross_tenant_leak | 0.0000 | [0.0000, 0.0000] |
| V2_vs_V3 | policy_violation | 0.0000 | [0.0000, 0.0000] |
