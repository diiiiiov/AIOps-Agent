# Review and arbitration commands

Record an independent review:

```powershell
python scripts/review_evaluation_case.py record --case-id AIOPS-0001 `
  --reviewer-id reviewer-a --decision approve --realism-score 4 `
  --notes "Evidence and root-cause mappings are complete."
```

Use repeatable `--fail-check` options for failed rubric items; such a review must
use `revise` or `reject`. When two reviewers disagree, a distinct third reviewer
records an arbitration:

```powershell
python scripts/review_evaluation_case.py arbitrate --case-id AIOPS-0001 `
  --arbitrator-id reviewer-c --decision revise `
  --rationale "The second root cause needs a separate supporting evidence item."
```

Summarize review coverage and arbitration status:

```powershell
python scripts/review_evaluation_case.py summary
```

All records are bound to the current dataset SHA-256. Regenerating or modifying
the dataset invalidates records under previous hash directories.
