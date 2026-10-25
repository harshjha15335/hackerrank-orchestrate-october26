# Evaluation report: Ghost Data Still Exists

Build: branch `feature/pre-m9-audit-fixes`. The pipeline is deterministic and makes no model calls (see `usage_report.md`).
All numbers below were measured on this build by `code/evaluation/pre_m9_metrics.py`; the raw output is
`code/evaluation/checkpoints/FINAL_METRICS.json`. The scorer (`code/evaluation/scorer.py`) is the only code that reads the public
sample answers. They are never an inference input.

**Submission readiness: FAIL.** The repository's strict contract validator rejects 77 of the 518 output rows (114 errors). See section 5.

## 1. Splits

| Split | Cases | How it was used |
|---|---|---|
| Development (dev) | the first 22 public sample cases by sorted `case_id` | Used for development and error analysis throughout. |
| Report-only holdout | the last 10 public sample cases | **Not blind.** These cases were inspected during earlier milestones, so their scores are reported only and are not evidence of generalisation. No rule was tuned on them. |
| Evaluation set | 518 requests in `dataset/deletion_requests.csv` | No answers are available. It is checked by the strict validator, determinism, citation and safety probes only. |

## 2. Sample accuracy (with screenshot evidence)

| Split | Status accuracy | Step precision | Step recall | Step F1 | Field accuracy | Sequence accuracy (exact steps) | Case exact match | Kendall tau (matched) | Cited evidence valid | Steps |
|---|---|---|---|---|---|---|---|---|---|---|
| dev | 19/22 (0.8636) | 0.9873 | 0.6446 | **0.7800** | 0.9469 | 0.0909 | 0.0909 | 1.0 | 25/25 | matched 78, predicted 79, gold 121 |
| holdout | 9/10 (0.9000) | 1.0000 | 0.7361 | **0.8480** | 0.9299 | 0.0000 | 0.0000 | 1.0 | 26/26 | matched 53, predicted 53, gold 72 |
| all | 28/32 (0.8750) | 0.9924 | 0.6788 | **0.8062** | 0.9400 | 0.0625 | 0.0625 | 1.0 | 51/51 | matched 131, predicted 132, gold 193 |

Matched-step field accuracy:
- dev: evidence_id 1.0000, operation 1.0000, phase 1.0000, resource_id 1.0000, state 1.0000, step_no 0.6282, system_id 1.0000
- holdout: evidence_id 0.9811, operation 1.0000, phase 1.0000, resource_id 1.0000, state 1.0000, step_no 0.5283, system_id 1.0000

Status mismatches (all 32): case_01 (gold COMPLETE, predicted INCOMPLETE), case_02 (gold COMPLETE, predicted INCOMPLETE), case_04 (gold COMPLETE, predicted INCOMPLETE), case_31 (gold COMPLETE, predicted INCOMPLETE). In each case the gold answer is COMPLETE and the pipeline reports INCOMPLETE because a required state or treatment could not be proven from evidence at `audit_at`. The pipeline fails closed.

Screenshot ablation (`--no-visual`) gives identical sample scores. On the 518 set, the output SHA-256 changes from `9d4e1aae861d26215d7aa19f9b28947fc0ef12d0744c247bf59801f9da406e0e` to `b001e0901fdafeb54a9a48a480cfe65f8d62a77c1e409bbfa8287c37da69effc`.

### Where recall is lost (dev and holdout misses, by cause)

| Cause | Missed gold steps |
|---|---|
| dev: linked: missing policy mapping | 3 |
| dev: linked: unknown conditional treatment | 18 |
| dev: linked: unknown state | 2 |
| dev: unlinked: mentioned only in evidence captured after audit_at | 2 |
| dev: unlinked: mentioned only in workflow activity rows (claims) | 8 |
| dev: unlinked: no participant evidence mentions the resource | 3 |
| dev: unlinked: only identifier-free records (positional or naming joins are not ownership) | 7 |
| holdout: linked: unknown conditional treatment | 2 |
| holdout: unlinked: mentioned only in evidence captured after audit_at | 4 |
| holdout: unlinked: mentioned only in workflow activity rows (claims) | 5 |
| holdout: unlinked: only identifier-free records (positional or naming joins are not ownership) | 8 |

"unknown conditional treatment" is mostly Rule 12 (security audit records with no supplied retention period) and Rule 05 (support messages whose conversation content is not in the evidence). The pipeline leaves these UNRESOLVED instead of guessing. "Identifier-free records" are joins the pipeline deliberately refuses to make: positional, naming or timing joins are not proof of ownership.

## 3. Full 518-case run

| Check | Result |
|---|---|
| Rows | 518, one per request, sorted, seven-field steps, consecutive `step_no` |
| Status | {"COMPLETE": 88, "INCOMPLETE": 420, "NOT_APPLICABLE": 10} |
| Determinism | run 1 `9d4e1aae861d26215d7aa19f9b28947fc0ef12d0744c247bf59801f9da406e0e` = run 2 `9d4e1aae861d26215d7aa19f9b28947fc0ef12d0744c247bf59801f9da406e0e` (identical: True) |
| Root `output.csv` from `python3 code/main.py` | same SHA-256 as run 1 |
| Citations | 809 checked, 809 accepted, 0 rejected |
| Strict validator | **FAIL: 114 errors in 77 rows** |
| INCOMPLETE rows with no steps | 37 |
| INCOMPLETE rows with steps but no FINDING | 40 |

## 4. Safety probes (518 run)

| Probe | Result |
|---|---|
| Resources that appear in the steps of more than one user | 0 |
| DELETE of a policy-retained / tombstone / legal-hold / backup / support-message record without a decided DELETE | 0 |
| DELETE of a record whose decided action is RETAIN | 0 |
| Cited VERIFY_RECORD_ANONYMIZED steps (evidence-backed anonymization claims) | 0 |
| ANONYMIZE items judged COMPLIANT | 0 |
| Accepted citations naming another person | 0 |

No P0 cross-customer contamination or false-COMPLIANT anonymization was found on the 518 run or by the adversarial tests below. This does not guarantee there are none: it covers only the probes and cases listed here.

## 5. Strict validation failures (all 77 rows)

The strict validator requires every INCOMPLETE row to have FINDING, REMEDIATION and VERIFICATION phases, with each finding paired with a remediation. These rows are INCOMPLETE because the pipeline cannot prove compliance. It also has no participant-visible evidence for a finding, so it emits no finding rather than invent one. The validator was not changed.

Class 5 means the obligation itself is undecidable from the supplied policy and evidence (for example, a Rule 12 retention period that does not exist). Class 4 means the treatment, current state, process state or ownership link is not evidenced at `audit_at`.

| Blocker | Rows |
|---|---|
| class 4: no admissibly linked subject-owned resource or process | 6 |
| class 4: process safe state shown only by inventory or not at all | 5 |
| class 4: rule_05: conversation content not observed (shared-context condition undecidable) | 19 |
| class 4: rule_14: no explicit restore control observed | 4 |
| class 4: treatment decided; no admissible reading of the current state | 10 |
| class 5: rule_12: no supplied retention period covering audit_at | 61 |
| class 5: rule_13: no supplied active legal hold with a basis | 1 |

| case | class | status | steps | errors | strict errors | blockers |
|---|---|---|---|---|---|---|
| case_103 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_107 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_108 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_111 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_112 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_135 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_137 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_155 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_157 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_162 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_204 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_206 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_233 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_235 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_253 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_257 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_260 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_264 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; rule_14: no explicit restore control observed |
| case_265 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_267 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_292 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_304 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_308 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_309 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_324 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_326 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_33 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_331 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_35 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_354 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_362 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_369 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_383 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_390 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; rule_13: no supplied active legal hold with a basis; rule_14: no explicit restore control observed; treatment decided; no admissible reading of the current state |
| case_392 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_403 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_408 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_409 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_41 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; rule_14: no explicit restore control observed; treatment decided; no admissible reading of the current state |
| case_411 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_412 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_44 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_45 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_456 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_457 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_458 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_462 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_480 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_484 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_50 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_506 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_51 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_512 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_516 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_52 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_520 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at |
| case_521 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_522 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at |
| case_543 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_545 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_547 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_549 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_55 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_14: no explicit restore control observed |
| case_57 | 5 | INCOMPLETE | 3 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_58 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_59 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_60 | 5 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at |
| case_61 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_63 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_76 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_77 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_81 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_82 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_83 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_84 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_86 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_88 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |

## 6. Team evaluation cases (independently constructed)

These cases were built by the team as synthetic fixtures. They are not taken from the public samples. Each one is an executable test, and all of them pass on this build.

| # | Case | Expected | Test |
|---|---|---|---|
| T1 | Subject's email plus another customer's phone on one record (the Codex reproduction) | M4 attribution `mixed_context`, state UNKNOWN; policy UNRESOLVED with no obligations for PRESENT, ABSENT or ANONYMIZED | `code/identity/tests/test_cross_customer.py`, `code/policy/tests/test_cross_customer_policy.py` |
| T2 | Foreign user ID, foreign email hash, nested foreign phone, phone with no known holder, shared historical alias | no supported state for the subject | `test_cross_customer.py` |
| T3 | Same person: current email, phone, hash, user ID and a historical phone on one record; historical email alias with current phone | supported (`direct_verified` / `direct`) | `test_cross_customer.py` |
| T4 | A support agent's email, phone and user reference in agent/assignee fields of the subject's ticket | the agent's identifiers are not customer identity; the subject's record stays attributable; the agent gets no supported state | `test_cross_customer.py` |
| T5 | Analytics record with identifier columns nulled, an ANONYMIZE_RECORD SUCCESS activity, and a `session_id` at top level, nested, deep, inside an array, suffixed (`source_session_id`) or as `linkage_key` | never ANONYMIZATION_EVIDENCED; UNKNOWN (INDIRECT_PRESENT) | `code/policy/tests/test_nested_identifiers.py` |
| T6 | The same nested session key copied next to the subject's email in another record (flat, nested, renamed) | TRUE (INDIRECT_LINKED), VIOLATION | `test_nested_identifiers.py` |
| T7 | Same key copied next to someone else's email; nested direct identifier; later nested identifying copy; activity SUCCESS with no field evidence | UNKNOWN / DIRECT_EXPOSED / not compliant / UNRESOLVED | `test_nested_identifiers.py` |
| T8 | Benign metrics (`sessions_30d`, `session_count`, floats, booleans under identifier names) with corroborated anonymization | not identities; FALSE, COMPLIANT (genuine anonymization still works) | `test_nested_identifiers.py` |

Earlier milestones added more adversarial fixtures: trace ownership (`code/identity/tests/test_trace_ownership.py`), anonymization proof (`code/policy/tests/test_anonymization.py`), citation guard (`code/synthesis/tests/test_pre_m9_guard.py`), and per-stage suites under each `code/*/tests` directory.

## 7. Failures found and improvements made

| Found by | Failure | Fix | Effect |
|---|---|---|---|
| Pre-M9 audit F-02 | Null identifier columns were accepted as proof of anonymization | Anonymization needs an ANONYMIZE_RECORD operation corroborated by a later source read, with no indirect identifier and no later identifying copy | No false COMPLIANT anonymization |
| Pre-M9 audit F-03 | Trace joins could pull in other people's lines | Trace joins require every identifier to be the subject's alone (identity graph) | No cross-user trace joins |
| Pre-M9 audit F-05 | Absence citations were not re-proved | The citation guard re-proves absence from the snapshot | 809/809 citations accepted |
| Pre-M9 audit F-06 | Post-cutoff screenshots were not reported | Reported in `excluded_visual` and never used | |
| Codex re-test | The support attachment-document rule (`support_001`) misread a reference as a classification | **Reverted**: a document that names a record does not classify it | Dev F1 0.798 -> 0.780 (accepted) |
| Codex re-test (P0) | A nested session/device/linkage ID bypassed the anonymization check (top-level only) | Recursive, type-aware detection of indirect, direct and stable-reference fields; link keys indexed the same way | No 518 output change; T5-T8 |
| Codex re-test (P0) | Subject email plus another customer's phone gave a supported M4 state | Every customer identifier must be the subject's; owner conflicts block every strength; agent/actor fields are not customer identity; `null`/redacted hash renderings ignored | No 518 output change; T1-T4 |

The two P0 fixes do not change the 518 output, so the evaluation data never exercises those paths. They close the paths for any input that does.

## 8. Limitations

- Strict validation fails on 77 rows (section 5). Closing them would need Rule 12 retention periods, Rule 05 conversation content, restore controls or state evidence that the dataset does not supply. Steps were not fabricated to pass the validator.
- Dev step F1 is 0.780 and exact sequence accuracy is 0.0909 (2/22). Recall is the weak side; precision is 0.987.
- The holdout is not blind.
- Screenshot facts come from committed manual fixtures, not runtime vision.
- The pipeline's behaviour against the hidden grader is unknown. Nothing here claims hidden-grader compliance.
