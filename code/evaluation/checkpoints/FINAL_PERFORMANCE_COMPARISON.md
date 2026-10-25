# Final performance comparison

Before is 3a2f78a. After is `feature/final-contract-performance-repair` with the Rule 12 owner decision. That decision is the only production logic change; it changes the full-run rows.

| Metric | Before | After |
|---|---|---|
| Tests passing | 600 | see FINAL_SAFETY_VERIFICATION.md |
| Strict-invalid rows | 77 | 33 |
| Strict errors | 114 | 42 |
| INCOMPLETE rows with no steps | 37 | 9 |
| INCOMPLETE rows without findings | 40 | 24 |
| Status (518) | {"COMPLETE": 88, "INCOMPLETE": 420, "NOT_APPLICABLE": 10} | {"COMPLETE": 132, "INCOMPLETE": 376, "NOT_APPLICABLE": 10} |
| Dev status accuracy | 19/22 | 19/22 |
| Dev step precision | 0.9873 | 0.9882 |
| Dev step recall | 0.6446 | 0.6942 |
| Dev step F1 | 0.78 | 0.8155 |
| Dev field accuracy | 0.9469 | 0.9439 |
| Dev exact sequences | 2/22 | 4/22 |
| Holdout status (report-only) | 9/10 | 10/10 |
| Holdout F1 (report-only) | 0.848 | 0.8661 |
| Citations accepted | 809/809 | 885/885 |
| Unsafe deletes / retained deletes | 0 / 0 | 0 / 0 |
| Compliant ANONYMIZE items (false-compliant risk) | 0 | 0 |
| Cross-user resources / foreign citations | 0 / 0 | 0 / 0 |
| 518 SHA-256 | 9d4e1aae861d26215d7aa19f9b28947fc0ef12d0744c247bf59801f9da406e0e | 252b026188daea2fe4b72a5bcbaaefe4dbd98c991bc40b53ecbedd4727352e3c |
| Runtime model calls | 0 | 0 |

The change relies on source facts: the supplied rule table has no DELETE rule for SECURITY_AUDIT_LOG. It is not tuned to answers.

An evaluation-only ablation (`code/evaluation/rule12_ablation.py`) that treated *every* UNKNOWN Rule 12 condition as TRUE, including records without field evidence, reached dev F1 0.8325. It was **rejected**, because it would retain records the evidence does not show.
