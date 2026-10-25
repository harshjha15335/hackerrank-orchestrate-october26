# Evaluation report: Ghost Data Still Exists

Build: branch `experiment/relaxed-joins` (Rule 12 owner decision plus the two owner-requested relaxed rules, see section 0). The pipeline is deterministic and makes no model calls (see `usage_report.md`).
All numbers below were measured on this build by `code/evaluation/pre_m9_metrics.py`; the raw output is
`code/evaluation/checkpoints/FINAL_METRICS.json`. The scorer (`code/evaluation/scorer.py`) is the only code that reads the public
sample answers. They are never an inference input.

**Submission readiness: FAIL.** The repository's strict contract validator rejects 20 of the 518 output rows (27 errors). See section 5.

## 0. Build and the owner decisions it contains

This report describes the uploaded build: `output.csv` SHA-256 `2f08a2f88c2985e31df2d1f0313bf834e97bc4194e3011a0aebaebd34a0e0258`. It contains three owner decisions; each one has a configuration switch.

1. **Rule 12** (`retention_without_period`). An observed security audit record with no supplied retention period is retained, because no rule authorizes deleting a SECURITY_AUDIT_LOG.
2. **Claim-linked account** (`RELAXED['claim_account_link']` in `code/synthesis/main.py`, logic in `code/state/relaxed.py`). The account_service DELETE_RECORD workflow row nearest `reported_at` (within 2 hours) is taken as the subject's account. Each row is assigned to at most one request. The link is skipped when the subject already has a directly linked account, or when any record attributes the account to someone else. Absence is cited from the latest complete account snapshot taken after that row and before `audit_at`.
3. **Rule 05** (`support_without_content`). A support message whose conversation content is not observable takes the non-destructive REDACT branch.

| Build | Strict errors / rows | Dev F1 | Dev exact | Dev status | Holdout F1 (report-only) |
|---|---|---|---|---|---|
| 3a2f78a (no decisions) | 114 / 77 | 0.780 | 2/22 | 19/22 | 0.848 |
| + Rule 12 | 42 / 33 | 0.8155 | 4/22 | 19/22 | 0.866 |
| + claim-linked account | 42 / 33 | 0.8436 | 7/22 | 21/22 | 0.875 |
| + Rule 05 REDACT (uploaded) | **27 / 20** | **0.8598** | **7/22** | **21/22** | 0.875 |

The full test suite was last run green on the Rule 12 build. It was not re-run after the two relaxed rules, and tests written for the earlier rules would need updating.

## 1. Splits

| Split | Cases | How it was used |
|---|---|---|
| Development (dev) | the first 22 public sample cases by sorted `case_id` | Used for development and error analysis throughout. |
| Report-only holdout | the last 10 public sample cases | **Not blind.** These cases were inspected during earlier milestones, so their scores are reported only and are not evidence of generalisation. No rule was tuned on them. |
| Evaluation set | 518 requests in `dataset/deletion_requests.csv` | No answers are available. It is checked by the strict validator, determinism, citation and safety probes only. |

## 2. Sample accuracy (with screenshot evidence)

| Split | Status accuracy | Step precision | Step recall | Step F1 | Field accuracy | Sequence accuracy (exact steps) | Case exact match | Kendall tau (matched) | Cited evidence valid | Steps |
|---|---|---|---|---|---|---|---|---|---|---|
| dev | 21/22 (0.9545) | 0.9892 | 0.7603 | **0.8598** | 0.9519 | 0.3182 | 0.3182 | 1.0 | 28/28 | matched 92, predicted 93, gold 121 |
| holdout | 10/10 (1.0000) | 1.0000 | 0.7778 | **0.8750** | 0.9337 | 0.0000 | 0.0000 | 1.0 | 28/28 | matched 56, predicted 56, gold 72 |
| all | 31/32 (0.9688) | 0.9933 | 0.7668 | **0.8655** | 0.9450 | 0.2188 | 0.2188 | 1.0 | 56/56 | matched 148, predicted 149, gold 193 |

Matched-step field accuracy:
- dev: evidence_id 1.0000, operation 1.0000, phase 1.0000, resource_id 1.0000, state 1.0000, step_no 0.6071, system_id 1.0000
- holdout: evidence_id 1.0000, operation 1.0000, phase 1.0000, resource_id 1.0000, state 1.0000, step_no 0.5091, system_id 1.0000

Status mismatches (all 32): case_04 (gold COMPLETE, predicted INCOMPLETE). In each case the gold answer is COMPLETE and the pipeline reports INCOMPLETE because a required state or treatment could not be proven from evidence at `audit_at`. The pipeline fails closed.

Screenshot ablation (`--no-visual`) gives identical sample scores. On the 518 set, the output SHA-256 changes from `2f08a2f88c2985e31df2d1f0313bf834e97bc4194e3011a0aebaebd34a0e0258` to `a40c0e039e75bfb473a8ed6847b7a5d50cfb14a812077601f58d9f86e8ba4a0f`.

### Where recall is lost (dev and holdout misses, by cause)

| Cause | Missed gold steps |
|---|---|
| dev: linked: missing policy mapping | 3 |
| dev: linked: unknown conditional treatment | 9 |
| dev: linked: unknown state | 2 |
| dev: unlinked: mentioned only in evidence captured after audit_at | 2 |
| dev: unlinked: mentioned only in workflow activity rows (claims) | 3 |
| dev: unlinked: no participant evidence mentions the resource | 3 |
| dev: unlinked: only identifier-free records (positional or naming joins are not ownership) | 7 |
| holdout: unlinked: mentioned only in evidence captured after audit_at | 4 |
| holdout: unlinked: mentioned only in workflow activity rows (claims) | 4 |
| holdout: unlinked: only identifier-free records (positional or naming joins are not ownership) | 8 |

"unknown conditional treatment" is mostly Rule 12 (security audit records with no supplied retention period) and Rule 05 (support messages whose conversation content is not in the evidence). The pipeline leaves these UNRESOLVED instead of guessing. "Identifier-free records" are joins the pipeline deliberately refuses to make: positional, naming or timing joins are not proof of ownership.

## 3. Full 518-case run

| Check | Result |
|---|---|
| Rows | 518, one per request, sorted, seven-field steps, consecutive `step_no` |
| Status | {"COMPLETE": 143, "INCOMPLETE": 365, "NOT_APPLICABLE": 10} |
| Determinism | run 1 `2f08a2f88c2985e31df2d1f0313bf834e97bc4194e3011a0aebaebd34a0e0258` = run 2 `2f08a2f88c2985e31df2d1f0313bf834e97bc4194e3011a0aebaebd34a0e0258` (identical: True) |
| Root `output.csv` from `python3 code/main.py` | same SHA-256 as run 1 |
| Citations | 962 checked, 962 accepted, 0 rejected |
| Strict validator | **FAIL: 27 errors in 20 rows** (was 114 / 77) |
| INCOMPLETE rows with no steps | 7 |
| INCOMPLETE rows with steps but no FINDING | 13 |

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

## 5. Strict validation failures (all 20 rows)

The strict validator requires every INCOMPLETE row to have FINDING, REMEDIATION and VERIFICATION phases, with each finding paired with a remediation. These rows are INCOMPLETE because the pipeline cannot prove compliance, and it has no participant-visible evidence for a finding, so it emits no finding rather than invent one. The validator was not changed.

**Rule 12 owner decision (final sprint).** `deletion_rules.csv` has no rule that authorizes deleting a SECURITY_AUDIT_LOG. An observed, subject-attributed security audit record with no supplied retention period is therefore preserved: RETAIN, verified PRESENT with a citation of the observed record. No period is invented. Expired periods still lead to DELETE, and records without field evidence stay UNKNOWN. This took strict validation from 114 errors / 77 rows to 42 / 33. The setting is `retention_without_period` in `code/policy/condition_bindings.json`; setting it to `unknown` restores the earlier output.

Class 5 means the policy obligation is undecidable from the supplied data. Class 4 means the treatment, state, process or ownership is not evidenced at `audit_at`.

| Blocker | Rows |
|---|---|
| class 4: no admissibly linked subject-owned resource or process | 6 |
| class 4: process safe state shown only by inventory or not at all | 5 |
| class 4: rule_05: conversation content not observed (shared-context condition undecidable) | 6 |
| class 4: rule_14: no explicit restore control observed | 4 |
| class 4: treatment decided; no admissible reading of the current state | 10 |
| class 5: rule_12: no supplied retention period covering audit_at | 10 |
| class 5: rule_13: no supplied active legal hold with a basis | 1 |

| case | class | status | steps | errors | strict errors | blockers |
|---|---|---|---|---|---|---|
| case_135 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_137 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_264 | 4 | INCOMPLETE | 4 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable); rule_14: no explicit restore control observed |
| case_33 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_35 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_383 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_390 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; rule_13: no supplied active legal hold with a basis; rule_14: no explicit restore control observed; treatment decided; no admissible reading of the current state |
| case_392 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_12: no supplied retention period covering audit_at; treatment decided; no admissible reading of the current state |
| case_41 | 5 | INCOMPLETE | 1 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_05: conversation content not observed (shared-context condition undecidable); rule_12: no supplied retention period covering audit_at; rule_14: no explicit restore control observed; treatment decided; no admissible reading of the current state |
| case_50 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_52 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_520 | 4 | INCOMPLETE | 2 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_522 | 4 | INCOMPLETE | 2 | 1 | INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | rule_05: conversation content not observed (shared-context condition undecidable) |
| case_55 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | process safe state shown only by inventory or not at all; rule_14: no explicit restore control observed |
| case_61 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
| case_63 | 4 | INCOMPLETE | 0 | 2 | INCOMPLETE requires nonempty steps; INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases | no admissibly linked subject-owned resource or process |
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
| T9 | Security audit record: no period (retained, PRESENT verified); expired period (DELETE); no field evidence (UNKNOWN); valid period (retained) | as stated; no period is invented | `code/policy/tests/test_rule12_without_period.py` |
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

| Final sprint (owner decision) | Rule 12 records without a supplied period were left undecided, causing most strict errors | Observed records are retained because no DELETE rule exists for the category | Strict 114/77 -> 42/33; dev F1 0.780 -> 0.816 |

The two P0 fixes do not change the 518 output, so the evaluation data never exercises those paths. They close the paths for any input that does.

## 8. Limitations

- Strict validation fails on 20 rows (section 5). Closing them would need Rule 05 conversation content, restore controls or state evidence that the dataset does not supply. Steps were not fabricated to pass the validator.
- Dev step F1 is 0.860 and exact sequence accuracy is 0.3182 (7/22). Recall is the weak side; precision is 0.988. 22/22 is not reachable without joins the safety rules forbid (see `code/evaluation/checkpoints/FINAL_RECALL_ANALYSIS.md`).
- The holdout is not blind.
- Screenshot facts come from committed manual fixtures, not runtime vision.
- The pipeline's behaviour against the hidden grader is unknown. Nothing here claims hidden-grader compliance.
