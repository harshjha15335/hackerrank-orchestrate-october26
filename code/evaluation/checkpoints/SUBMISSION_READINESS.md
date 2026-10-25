# Submission readiness report (final sprint, 2026-10-25)

**Readiness: FAIL.** The repository's strict contract validator rejects 77 of 518 rows (114 errors). Everything is packaged for owner inspection. Nothing has been submitted or uploaded.

## Verdict by item

| Item | Status | Detail |
|---|---|---|
| P0 nested-identifier anonymization bypass | Fixed | Recursive, type-aware detection; T5-T8 in `evaluation/evaluation_report.md` |
| P0 subject email + foreign phone gives supported M4 state | Fixed | Owner conflict and foreign identifiers block every strength; T1-T4 |
| Attachment-document rule (`support_001`) | Reverted | Dev F1 back to 0.780 |
| Safety probes on 518 | Pass | 0 cross-user resources, 0 unsafe deletes, 0 retained-record deletes, 0 compliant ANONYMIZE items, 0 accepted foreign citations |
| Citations | Pass | 809/809 accepted |
| Test suite | Pass | 600 passed, 0 failed (`python3 -m pytest -q code`) |
| Determinism | Pass | Two runs and a clean run from the extracted `code.zip` produce the same SHA-256, `9d4e1aae861d26215d7aa19f9b28947fc0ef12d0744c247bf59801f9da406e0e` |
| `output.csv` format | Pass | 518 rows, sorted, header `case_id,deletion_status,steps_json`, seven-field steps, consecutive step numbers |
| Strict contract validator | **FAIL** | 114 errors in 77 rows: 57 class 5 (Rule 12 retention / Rule 13 legal hold undecidable), 20 class 4 (state, content or restore evidence missing). Full list in the evaluation report, section 5 |
| `code.zip` | Built | Contains `README.md`, `evaluation/evaluation_report.md`, `evaluation/usage_report.md` and `code/`. Excludes dataset, caches, venvs, credentials, CSVs and metrics JSON (which carry sample-answer step keys) |
| Clean environment | Pass | `env -i python3 -I code/main.py` in an empty directory with `code.zip` extracted and `dataset/` copied in. Python 3.13.17, pdftotext 24.02.0, standard library only |
| Usage report | Factual | 0 model calls, 0 tokens, $0 |
| Transcript | Present | Root `log.txt` |
| Hidden-grader compliance | **Unknown** | Not claimed |

## Why strict still fails

These rows are INCOMPLETE because compliance cannot be proven. They also lack participant-visible evidence for a finding, so the validator's requirement of FINDING, REMEDIATION and VERIFICATION cannot be met without inventing a finding, a retention period or a restore permission. That is prohibited. The validator was not changed. The owner must decide on this contract question before submitting.

## Remaining unsafe or unverified

- The 77 strict-invalid rows. 37 are INCOMPLETE with no steps, and 40 have only future verification checks.
- The P0 fixes do not change the 518 output. The evaluation data never reaches those paths, so the fixes are proven only by synthetic tests.
- The holdout is not blind. Screenshots use manual fixtures. Dev recall is 0.645.
- Support-agent field names are matched by a name pattern (`agent`, `assignee`, `operator`, ...). The dataset has no such fields, so this is untested on real evidence.
