# Evaluation dataset quality report (draft v1)

- Dataset SHA-256: `3b05177b805bc0a8d4200e3adeabfb0c5eed4c320488ef646857877e77fb3768`
- Total cases: 1000
- Split: development 200, sealed_test 800
- Root cause mode: single 700, multiple 300
- Cross-tenant risk: 250
- Review status: {'draft': 1000}

## Diversity gates

| Gate | Result | Status |
|---|---:|---|
| Unique prompts | 1000 | PASS |
| Unique services | 50 | PASS |
| Scenario families | 250 | PASS |
| Unique evidence texts | 3550 | PASS |
| Largest family | 6 | PASS (limit 6) |

## Category distribution

| Category | Total | Cross-tenant | Multiple |
|---|---:|---:|---:|
| api_latency_timeout | 140 | 28 | 42 |
| business_error | 100 | 20 | 30 |
| cpu_saturation | 90 | 18 | 27 |
| database | 120 | 26 | 36 |
| deployment_configuration | 100 | 22 | 30 |
| memory_oom | 90 | 18 | 27 |
| network_dependency | 110 | 24 | 33 |
| security_tenant | 50 | 50 | 15 |
| service_availability | 130 | 28 | 39 |
| storage_queue_capacity | 70 | 16 | 21 |

## Release decision

**NOT APPROVED FOR FORMAL BENCHMARKING.** The file contains synthetic draft cases. Schema, quota and exact-duplicate gates pass, but two-person review, semantic near-duplicate analysis and gold-label adjudication are not complete.
