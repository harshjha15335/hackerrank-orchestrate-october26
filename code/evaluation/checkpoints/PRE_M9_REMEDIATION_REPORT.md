# Pre-M9 audit remediation report

Branch `feature/pre-m9-audit-fixes`, from audited main `cccb59e31c253c0df49b2e00138d1a765c357c93`.
Written by Claude Code for the independent Codex re-test. Nothing here was merged, and M9 and M10 were not started.
Root `output.csv` and `dataset/` are unchanged. All earlier reports are kept as they were.

## Verdict

**HOLD: NOT SUBMISSION-READY. The branch is ready for the independent re-test.**

- The two confirmed defects are fixed and covered by adversarial tests: unsafe anonymization inference (F-02) and missed same-person trace joins (F-03).
- The absence-citation guard is hardened (F-05). Screenshots captured after `audit_at` now appear in the diagnostics (F-06).
- The reassessment found one more policy misreading, and it is fixed. In Rule 05, `[REDACTED]` message text had been read as "content without shared context", which decided a DELETE.
- The strict M0 validator still fails, with **114 errors in 77 rows**. Of those rows, 57 are blocked by facts the participant data does not supply (class 5). The other 20 are blocked by evidence that is genuinely missing (class 4). No class 1–3 cause remains open.
- Development step F1 is **0.798**, against a target of 0.80, so it is still **unmet**. Without the one judgment-call rule described in §2.4, it is 0.780.
- The runtime makes **0 model calls**.

## 1. Audit issues and resolution status

| Audit item | Remediation priority | Status | 518-row effect |
|---|---|---|---|
| F-02 unsafe anonymization inference | P0 | **Fixed** (§2.1) | 0 rows. The defect was latent: no linked analytics or telemetry copy reached the null-column path in this dataset |
| F-03 missed same-customer trace links | P0 | **Fixed** (§2.2) | 0 rows. No trace in the dataset names two of one subject's identifiers |
| Unmapped `support_9251` / `support_8538` (2 cases) | P1 | **Mapped to SUPPORT_MESSAGE**. Rule 05 condition stays **UNKNOWN** (§2.3) | 0 rows. 15 resources move from "no category" to "condition UNKNOWN" |
| Recall / missing steps | P1 | **Investigated** (§4). No missed subject-naming evidence. One general document-category gap fixed (§2.4, judgment call) | 0 rows. 1 sample row |
| 77 strict-invalid cases | P0 | **Reassessed** (§5, appendix). One policy misreading fixed (§2.5). The rest are classified, and the contract ambiguity is documented (§6) | 1 row (the `support_9996` case) |
| F-05 absence citation guard | P2 | **Hardened** (§2.6) | 0 rows. No table-absence citation is emitted on the 518 |
| F-06 future-image diagnostics | P2 | **Fixed** (§2.7) | 0 rows. No subject-matching screenshot is captured after its case's cutoff |

## 2. Source-grounded code changes

### 2.1 F-02: anonymization needs evidence, not null columns

The Rule 07/08 predicate `still_attributable` used to return FALSE ("no longer attributable", so COMPLIANT) whenever two identifier columns were explicitly null and analytic content remained. Nulling columns in place keeps the record's resource key. Earlier copies, backups and the very link that tied the record to the subject can therefore still join that key to the person. That is pseudonymisation, not irreversible unlinking.

`code/policy/conditions.py::anonymization_state` now classifies the state-establishing copy into one of these states:

| State | Outcome | Basis |
|---|---|---|
| `DIRECT_EXPOSED` | TRUE | A direct identifier or stable reference is still populated |
| `INDIRECT_LINKED` | TRUE | An indirect identifier (configured in `condition_bindings.json` → `anonymization.indirect_identifier_fields`) has a value that another admissible record names together with the subject's own identifiers |
| `INDIRECT_PRESENT` | UNKNOWN | An indirect identifier remains, but nothing shows whether it re-links |
| `DIRECT_REMOVED` | UNKNOWN | Identifier columns are explicitly emptied, but no corroborated operation exists, or a copy naming the subject was observed at or after this read or after the operation |
| `NOT_DISPLAYED` | UNKNOWN | No identifier column is shown at all. Absence of a column is not removal |
| `ANONYMIZATION_EVIDENCED` | FALSE | Requires all of: an `ANONYMIZE_RECORD` activity on the same system and resource, reported `SUCCESS`, at or before the source read and admissible at `audit_at`; a later source read whose identifier columns are removed; no indirect identifier; and no later copy naming the subject |
| `UNRESOLVED` | UNKNOWN | No state-establishing field set |

The proof uses only participant data: the activity table's own operation type, and an independent source read that post-dates it. The activity row is still treated as a claim. It counts only because the later read corroborates it. No anonymization flag was invented.

Other changes:

- `engine._comply` no longer marks an ANONYMIZE copy COMPLIANT because a column is null. It reuses the same classification. `DIRECT_EXPOSED` and `INDIRECT_LINKED` give VIOLATION.
- The citation guard rejects `VERIFY_RECORD_ANONYMIZED` unless M5 recorded the corroborated anonymization (`anonymization_proven`).
- The M4 state label `ANONYMIZED` for identifier-free analytics rows is unchanged. Its meaning is "no direct identifier displayed", and it can no longer prove compliance on its own.

**Changed decisions.** The 518 run has none, and neither does the sample run. Before and after the change, no Rule 07/08 copy had a FALSE outcome: 69 were TRUE (exposed) and 20 were UNKNOWN. Two M5 fixtures in `test_policy.py` encoded the defect (null columns gave COMPLIANT). They now expect UNKNOWN/UNRESOLVED, and FALSE is covered by the operation-corroborated fixtures.

### 2.2 F-03: trace joins resolve ownership through the identity graph

`EvidenceIndex._find` used to reject any trace group naming more than one distinct email or user ID value. That included one subject's own email together with their user ID.

The changes:

- `IdentityGraph.owners()` (new) returns every user who has ever held an identifier, from the snapshot and from both sides of each audited change.
- `EvidenceIndex(..., graph=...)` accepts a trace only if every identifier in its admissible lines (email, user ID, phone, hash) is the resolved subject's at the cutoff and held by nobody else.
- A foreign, unknown, shared or later-acquired identifier keeps the trace ambiguous. This is stricter than before, because phones and hashes now count.
- Without the graph, the old conservative rule applies.
- Trace groups are still scoped to the same file, and future lines neither anchor nor contest a trace.
- At record level, `Hit.owner_conflict` keeps a same-record email and user ID that belong to two people as `mixed_context`.

All production entry points pass the graph: synthesis, policy, flow, state and the identity CLI. Across the 518 cases this changed 0 joins, 0 assertions and 0 rows.

### 2.3 Phase 3: `support_9251` / `support_8538` (`message_pii_scan`)

The only participant evidence for these two records is one owning-service log line each, in `evidence_48`:

```
support_platform | message_pii_scan | resource_id="support_8538" matched_value="<subject email>" detector="direct_identifier"
```

There are also two activity rows, `REDACT_RECORD FAILED`. Those are workflow claims, and they were not used.

**What the logs establish.** The owning service ran a message scan on the resource, so the record is a support message. Across the dataset, the 14 `message_pii_scan` resources with other category signals are all SUPPORT_MESSAGE, with 0 contradictions. In contrast, `attachment_pii_scan` names a `file` attached to the scanned record. Two of those records are evidenced conversations, so that event does not classify the record, and it is deliberately not mapped.

A declarative `scan_event_signals` entry (`message_pii_scan` → SUPPORT_MESSAGE, owning `support_platform` only) is ranked below every record-level signal. It maps 15 resources in the 518 cases, including the 2 named in the audit.

**What is still missing.** Rule 05 asks whether the conversation contains shared customer, agent or order context. The scan shows no message content, so the condition stays UNKNOWN. Both branches (REDACT if TRUE, DELETE if FALSE) require the subject's email to be gone, so the case is correctly INCOMPLETE. However, the finding operation itself depends on the undecided branch: REPORT_EXPOSED_PII or REPORT_REMAINING_RECORD. See §6.

### 2.4 Phase 4: support document that describes itself as an attachment (judgment call)

`evidence_58` is a PDF exported by `support_platform` (manifest origin). M1 joins it to `support_001` only because it names a single subject. Its own text reads "Attachment properties and upload history", with "Detail uploader customer".

A declarative `document_signals` entry classifies such a document's resource as SUPPORT_ATTACHMENT. Every pattern must match, the owning origin must match, and the document must be joined by M1 to that resource. In addition, `attachment_subject_only` reads the document's identity claims, which are single-subject by M1 construction.

The existing M7 artifact risk reading then supplies the finding (`REPORT_REMAINING_RECORD`, citing `evidence_58`).

- It affects **0 of 518 rows** and 1 sample row (dev).
- It raises dev F1 from 0.780 to 0.798.
- It was found through dev error analysis.

It is general and declarative, and it was not built from any answer value. It sits in its own commit (`Pre-M9 Phase 4 …`) so the reviewer can drop it independently if it reads as tuning.

### 2.5 Phase 5 finding: redacted message text decided a DELETE

`shared_support_context` treated `message_text="[REDACTED]"` as observed content with no shared context. That made Rule 05 FALSE, so `DEFAULT_ERASURE` gave DELETE.

Redacted text hides whatever context the message had, so it now counts as not observed. This was the only FALSE Rule 05 outcome in the 518 cases: `support_9996` in `evidence_25` line 24. That case keeps INCOMPLETE but loses one uncited future check (`VERIFY_RECORD_ABSENT support_9996`), which had come from the unsupported DELETE. This change is classed as **3 (incorrect policy interpretation)**.

### 2.6 F-05: absence citations are re-proved by the guard

`CitationGuard._absence` used to accept any `<table>:no-row:<resource>` locator whose table name existed in the file and lacked the row. It now also requires all of the following:

- The provenance scope equals the cited table, so the citation describes the copy the step relies on.
- The table belongs to the step's system (`state.engine.table_system`).
- The table scope is admissible at `audit_at` (`SnapshotIndex.scope`).
- The table is a verified complete point-in-time snapshot, using the same `authoritative_sql_scope` test M4 uses.
- Another admissible table row of the same snapshot independently names the resource with the subject's identifiers only.

Without a snapshot index, completeness cannot be verified and the citation is rejected. The positive fixture (a valid complete-snapshot absence) is preserved. On the 518 and sample runs there are 0 absence citations, so 0 change.

### 2.7 F-06: future-captured screenshots are reported

`EvidenceIndex._find` used to drop any observation captured after the cutoff before the screenshot check, so `excluded_visual` never listed such screenshots. Screenshot rows captured after `audit_at` are now returned as excluded, with the reason `captured after audit_at`. They still link nothing. Non-image future evidence is still neither found nor reported.

In this dataset, no subject-matching screenshot is captured after its case's cutoff, so the 4 existing excluded entries are unchanged.

## 3. Before / after measurements

The baseline is audited main `cccb59e`, reproduced in this session. The "after" column is this branch (`code/evaluation/checkpoints/PRE_M9_METRICS.json`, from `python3 code/evaluation/pre_m9_metrics.py`).

| Measurement | Before (cccb59e) | After |
|---|---|---|
| Regression tests | 509 passed | **565 passed, 0 failed** (56 new) |
| 518 output SHA-256 | `a45cdcf0…` | `9d4e1aae…`, identical across two independent runs |
| `--no-visual` ablation SHA-256 | `aeb5c135…` (M7) | `b001e090…` (M7 plus the `support_9996` row only) |
| 518 rows changed | — | 1 (`support_9996` case: one uncited future check removed) |
| Status COMPLETE / INCOMPLETE / NOT_APPLICABLE | 88 / 420 / 10 | 88 / 420 / 10 |
| Strict M0 validator | FAIL, 114 errors / 77 rows | FAIL, 114 errors / 77 rows |
| Nonstandard diagnostic validator (not for submission claims) | 0 errors | 0 errors |
| INCOMPLETE with empty steps / without FINDING | 37 / 40 | 37 / 40 |
| Dev step P / R / F1 | 0.9873 / 0.6446 / 0.780 | 0.9878 / 0.6694 / **0.798** (0.780 without §2.4) |
| Dev matched / predicted / gold | 78 / 79 / 121 | 81 / 82 / 121 |
| Dev missed / extra steps | 43 / 1 | 40 / 1 |
| Dev exact sequence accuracy | 2/22 | 2/22 |
| Dev status accuracy | 19/22 | 19/22 |
| Dev normalised Kendall agreement (matched steps) | 1.0 | 1.0 |
| Holdout F1 / status / sequence (report-only, not blind) | 0.848 / 9/10 / 0/10 | 0.848 / 9/10 / 0/10 |
| Citations checked / accepted / rejected (518) | 809 / 809 / 0 | 809 / 809 / 0 |
| Linked (case, resource) items (518) | 1252 | 1252 (0 newly linked, 0 lost) |
| Unresolved items / M4 UNKNOWN latest copies | 334 / 310 | 334 / 310 |
| UNKNOWN-treatment items, all cases / in no-finding rows | 268 / 82 | 284 / 85 (+15 scan-mapped supports now "condition UNKNOWN", +1 `support_9996`) |
| Screenshot ablation: sample rows changed by visual evidence | 0 | 0 |
| Runtime model calls / tokens / cost | 0 / 0 / $0 | 0 / 0 / $0 (M3 offline rules, M8 manual fixtures) |

**Dev misses by operation (after).**

| Operation | Missed |
|---|---|
| VERIFY_RECORD_ABSENT | 12 |
| VERIFY_RECORD_PRESENT | 12 |
| REPORT_EXPOSED_PII / REDACT_RECORD / VERIFY_RECORD_REDACTED | 3 each |
| VERIFY_RECORD_ANONYMIZED | 3 |
| REPORT_REMAINING_RECORD / DELETE_RECORD | 2 each |

The one extra step is the `account_6523` verification in a dev case. This is unchanged since M7.

**Safety probes on the 518 (after).** Every count below is 0:

- resources appearing in the steps of more than one user;
- DELETE without a decided DELETE treatment;
- DELETE of a policy-retained record;
- cited VERIFY_RECORD_ANONYMIZED steps;
- COMPLIANT ANONYMIZE items;
- accepted citations naming another person.

## 4. Recall investigation (Phase 4)

Every missed sample step was traced to a general cause, using participant evidence only. The answers were used only for scoring and to list the misses (`pre_m9_metrics.miss_cause`).

| Cause | Dev | Holdout |
|---|---|---|
| Linked, but the policy condition is UNKNOWN (Rule 12 retention: owner decision; Rule 05 shared context) | 18 | 2 |
| Linked, treatment decided, no admissible reading of the current state | 2 | 0 |
| Unlinked: the resource appears only in identifier-free records. The only joins are array position or naming, which are not ownership (M2 test `test_array_position_across_services_is_not_a_join`) | 7 | 8 |
| Unlinked: only workflow activity rows mention the resource (claims; joins would rest on timing alone) | 8 | 5 |
| Unlinked: only evidence captured after `audit_at` mentions it | 2 | 4 |
| Unlinked: no participant evidence mentions the resource at all | 3 | 0 |
| **Missed: admissible evidence names the subject and the resource** | **0** | **0** |

Sequence accuracy is limited by these missing steps, not by ordering. Every pairwise order among matched steps agrees (normalised Kendall 1.0).

The remaining dev recall gap cannot be closed under the project's attribution and temporal rules without adopting one of these:

1. a positional or timing join;
2. post-cutoff evidence;
3. a retention or shared-context assumption.

All three are excluded by standing owner decisions, so none was adopted.

Two observations for the reviewer:

- Several answer verifications cite identifier-free analytics rows as VERIFY_RECORD_ANONYMIZED. That is the null-column inference F-02 removes. Those resources are not linked by our pipeline anyway, so the F-02 metric cost is 0.
- The 10 previously inspected holdout cases stayed report-only, and nothing targets them.

## 5. The 77 strict-invalid cases (Phase 5)

The audit's partition was 6 cases with no linked resource, 2 unmapped and 69 unresolved. After this branch it is **6 / 0 / 71**: the 2 unmapped cases are now mapped and blocked by the Rule 05 condition.

The script assigns each case the weakest class among its blockers (`strict_invalid_cases` in `PRE_M9_METRICS.json`):

| Class | Cases |
|---|---|
| 1 correctable implementation defect | 0 open |
| 2 missed admissible evidence | 0 open |
| 3 incorrect policy interpretation | 0 open (1 fixed: §2.5) |
| 4 genuine missing evidence | 20 |
| 5 irreducible uncertainty under the participant contract | 57 |

Blockers across the 77 cases:

| Blocker | Class | Count |
|---|---|---|
| Rule 12: no supplied retention period covering `audit_at` (owner decision: stays UNRESOLVED) | 5 | 61 |
| Rule 13: no supplied active legal hold with a basis | 5 | 1 |
| Rule 05: conversation content not observed | 4 | 19 |
| Treatment decided, no admissible reading of the current state | 4 | 10 |
| No admissibly linked subject-owned resource or process | 4 | 6 |
| Process safe state shown only by inventory listings, or not at all (M6 asymmetric proof) | 4 | 5 |
| Rule 14: no explicit restore control observed | 4 | 4 |

The per-case appendix is at the end of this report. None of the 61 retention-blocked audit records has a retention field or a document block anywhere in the participant data, at any time. No FINDING, DELETE, REDACT, ANONYMIZE or RETAIN decision, retention period or restore permission was fabricated, and the strict validator is unchanged.

## 6. Unresolved official-contract interpretation

The strict validator, which follows the problem statement, requires an INCOMPLETE row to contain FINDING, REMEDIATION and VERIFICATION steps. A FINDING must cite evidence proving a record present or exposed, or a process active, at `audit_at`. For 77 rows the evidence supports INCOMPLETE because completeness cannot be proven, but supports no specific finding:

1. **Undecidable conditional treatment.** Rule 05 has a REDACT branch and a DELETE branch, and both require the subject's identifiers gone. A scan or listing shows the email present, so a violation is certain, but the finding operation (REPORT_EXPOSED_PII or REPORT_REMAINING_RECORD) and the remediation depend on a condition the evidence cannot decide. The contract has no operation for "identifiers present, treatment undecided".
2. **Supplied-fact conditions.** Rule 12 and Rule 13 need a supplied retention period or hold, and the data supplies none (owner decision 2026-10-24). Neither RETAIN, which would assume retention, nor DELETE, which would assume expiry, is evidenced.
3. **No proven current state.** The treatment is decided but no admissible, subject-owned reading shows the record present, exposed or absent. A finding would assert an unproven state, and COMPLETE would assert unproven compliance.
4. **No linked resource.** The subject resolves (or not), but no participant evidence ties a resource to them at the cutoff. Calling the case COMPLETE would claim completeness with nothing verified.

Under the strict contract each row has three options: fabricate a finding, claim COMPLETE, or stay INCOMPLETE with an invalid plan shape. Only the last is honest. Whether the official grader accepts an INCOMPLETE row with only future verifications (40 rows) or `[]` (37 rows) is an **open question for Harsh**.

## 7. Effect on M0–M8 guarantees

| Milestone | Effect |
|---|---|
| M0 schema / strict validator | Unchanged, and the validator was not modified |
| M2 customer attribution | Stricter. Trace joins need exclusive graph ownership, and phones and hashes now count. Same-subject email and user ID join correctly |
| M4 physical-copy isolation | Unchanged. The absence guard now also checks the copy scope |
| M5 retention / legal hold | Unchanged. Rule 07/08 FALSE needs corroborated anonymization. Rule 05 ignores redacted text. Categories added for scans and attachment documents |
| M6 flow / restore ordering | Unchanged |
| M7 citation proof | Stricter. Absence and anonymized citations are re-proved. 809/809 citations are still accepted |
| M8 screenshot quarantine / provenance | Unchanged. Future-captured screenshots are now reported. Manual screenshot fixtures were not modified |
| Pinned hashes | `test_vision.py` now pins the new 518 hash and ablation hash, with the M7/M8 hashes kept for reference. The only difference is the `support_9996` row |

## 8. New tests and outcomes

The full suite is `python3 -m pytest -q -p no:cacheprovider code`, with **565 passed** and 0 failed.

| File | Tests | Covers |
|---|---|---|
| `code/policy/tests/test_anonymization.py` | 19 | F-02. Positive (corroborated operation) and negative cases (null columns, not displayed, failed or mismatched or future operation, operation after the read). Indirect link to the subject versus to someone else, and a future link record. Historical copy before and after the operation, multiple copies (worst copy), missing state, telemetry |
| `code/identity/tests/test_trace_ownership.py` | 14 | F-03. Same-person email and user ID, historical alias, cross-person trace, foreign customer inheriting, same-record two subjects, unknown or shared or foreign-phone identifier, identifier-free downstream, trace ID across files, future anchor and contester, alias gained after the cutoff |
| `code/policy/tests/test_scan_category.py` | 10 | Phase 3/4/5. Scan mapping and its limits (attachment scan, other service or resource, rank), scan leaves Rule 05 UNKNOWN, attachment documents and their limits, redacted text is not content |
| `code/synthesis/tests/test_pre_m9_guard.py` | 13 | F-05. Valid absence preserved; incompleteness, missing index, foreign or no attribution, wrong copy, absent table, other system, row still present, future snapshot all rejected. F-02 citation rule. F-06 future screenshot excluded and reported, non-image future evidence not reported |

## 9. Verification performed (Phase 7)

1. Complete regression suite: 565 passed.
2. New adversarial tests: 56 passed (included in item 1).
3. Two independent 518-case executions: byte-identical (`9d4e1aae…`).
4. Strict M0 validation: FAIL, 114 errors / 77 rows, reported as measured.
5. Development and report-only holdout evaluation: §3.
6. Screenshot ablation: `--no-visual` hash `b001e090…`. Visual evidence changes 0 sample rows.
7. Citation validity: 809/809 accepted, 0 rejected.
8. Cross-customer contamination: no resource appears in the steps of two users, and no accepted citation names another person.
9. Negative safety probes: 0 unauthorized deletions, 0 deletions of retained records, 0 false-compliant anonymizations, 0 cited anonymized verifications.

Runtime model use is 0 calls, 0 tokens and $0. Intent classification uses offline rules (0 requests routed to a model), and screenshot extraction uses committed manual fixtures.

## 10. M9 handoff

See `code/evaluation/checkpoints/PRE_M9_M9_HANDOFF.md`.

## Appendix: remaining strict-invalid cases (generated)

Class: 4 = genuine missing evidence, 5 = irreducible uncertainty under the participant contract. "Steps" is the row's step count.

| case | class | status / steps | blockers (resource: cause) |
|---|---|---|---|
| case_33 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_35 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_41 | 5 | INCOMPLETE / 1 | account_service/account_4051: treatment decided; no admissible reading of the current state; backup_service/backup_706: rule_14: no explicit restore control observed; security_service/audit_record_7814: rule_12: no supplied retention period covering audit_at; support_platform/support_2667: rule_05: conversation content not observed (shared-context condition undecidable); backup_service/backup_706: process safe state shown only by inventory or not at all; integration_service/data_flow_2901: process safe state shown only by inventory or not at all |
| case_44 | 4 | INCOMPLETE / 4 | support_platform/support_1066: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_45 | 5 | INCOMPLETE / 1 | security_service/audit_record_001: rule_12: no supplied retention period covering audit_at; security_service/audit_record_002: rule_12: no supplied retention period covering audit_at; security_service/audit_record_004: rule_12: no supplied retention period covering audit_at; security_service/audit_record_005: rule_12: no supplied retention period covering audit_at; security_service/audit_record_006: rule_12: no supplied retention period covering audit_at |
| case_50 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_51 | 4 | INCOMPLETE / 4 | support_platform/support_1097: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_52 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_55 | 4 | INCOMPLETE / 0 | backup_service/backup_9287: rule_14: no explicit restore control observed; backup_service/backup_9287: process safe state shown only by inventory or not at all |
| case_57 | 5 | INCOMPLETE / 3 | security_service/audit_record_7219: rule_12: no supplied retention period covering audit_at |
| case_58 | 5 | INCOMPLETE / 0 | security_service/audit_record_8465: rule_12: no supplied retention period covering audit_at |
| case_59 | 5 | INCOMPLETE / 0 | security_service/audit_record_962: rule_12: no supplied retention period covering audit_at |
| case_60 | 5 | INCOMPLETE / 0 | security_service/audit_record_629: rule_12: no supplied retention period covering audit_at |
| case_61 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_63 | 4 | INCOMPLETE / 0 | —: no admissibly linked subject-owned resource or process |
| case_76 | 4 | INCOMPLETE / 0 | support_platform/support_9746: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_77 | 4 | INCOMPLETE / 4 | support_platform/support_008: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_81 | 4 | INCOMPLETE / 4 | support_platform/support_5953: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_82 | 4 | INCOMPLETE / 4 | support_platform/support_9166: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_83 | 5 | INCOMPLETE / 1 | account_service/account_2449: treatment decided; no admissible reading of the current state; security_service/audit_record_2636: rule_12: no supplied retention period covering audit_at |
| case_84 | 5 | INCOMPLETE / 1 | account_service/account_2387: treatment decided; no admissible reading of the current state; security_service/audit_record_3787: rule_12: no supplied retention period covering audit_at |
| case_86 | 5 | INCOMPLETE / 1 | account_service/account_8473: treatment decided; no admissible reading of the current state; security_service/audit_record_5580: rule_12: no supplied retention period covering audit_at |
| case_88 | 5 | INCOMPLETE / 1 | account_service/account_868: treatment decided; no admissible reading of the current state; security_service/audit_record_3825: rule_12: no supplied retention period covering audit_at; support_platform/support_2967: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_103 | 5 | INCOMPLETE / 0 | security_service/audit_record_9522: rule_12: no supplied retention period covering audit_at |
| case_107 | 5 | INCOMPLETE / 0 | security_service/audit_record_7572: rule_12: no supplied retention period covering audit_at |
| case_108 | 5 | INCOMPLETE / 0 | security_service/audit_record_1469: rule_12: no supplied retention period covering audit_at |
| case_111 | 5 | INCOMPLETE / 0 | security_service/audit_record_8933: rule_12: no supplied retention period covering audit_at |
| case_112 | 5 | INCOMPLETE / 3 | security_service/audit_record_4082: rule_12: no supplied retention period covering audit_at |
| case_135 | 5 | INCOMPLETE / 1 | account_service/account_1417: treatment decided; no admissible reading of the current state; security_service/audit_record_5140: rule_12: no supplied retention period covering audit_at |
| case_137 | 5 | INCOMPLETE / 1 | account_service/account_3734: treatment decided; no admissible reading of the current state; security_service/audit_record_6779: rule_12: no supplied retention period covering audit_at |
| case_155 | 5 | INCOMPLETE / 3 | security_service/audit_record_4199: rule_12: no supplied retention period covering audit_at |
| case_157 | 5 | INCOMPLETE / 0 | security_service/audit_record_8821: rule_12: no supplied retention period covering audit_at |
| case_162 | 5 | INCOMPLETE / 0 | security_service/audit_record_6362: rule_12: no supplied retention period covering audit_at |
| case_204 | 5 | INCOMPLETE / 3 | security_service/audit_record_2736: rule_12: no supplied retention period covering audit_at |
| case_206 | 5 | INCOMPLETE / 0 | security_service/audit_record_9878: rule_12: no supplied retention period covering audit_at |
| case_233 | 4 | INCOMPLETE / 4 | support_platform/support_9670: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_235 | 4 | INCOMPLETE / 4 | support_platform/support_9391: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_253 | 5 | INCOMPLETE / 0 | security_service/audit_record_2927: rule_12: no supplied retention period covering audit_at |
| case_257 | 5 | INCOMPLETE / 0 | security_service/audit_record_7193: rule_12: no supplied retention period covering audit_at |
| case_260 | 5 | INCOMPLETE / 0 | security_service/audit_record_1876: rule_12: no supplied retention period covering audit_at |
| case_264 | 5 | INCOMPLETE / 3 | backup_service/backup_3250: rule_14: no explicit restore control observed; security_service/audit_record_6711: rule_12: no supplied retention period covering audit_at; support_platform/support_9996: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_265 | 5 | INCOMPLETE / 1 | security_service/audit_record_6378: rule_12: no supplied retention period covering audit_at |
| case_267 | 5 | INCOMPLETE / 1 | security_service/audit_record_6621: rule_12: no supplied retention period covering audit_at |
| case_292 | 4 | INCOMPLETE / 4 | support_platform/support_1526: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_304 | 5 | INCOMPLETE / 0 | security_service/audit_record_4759: rule_12: no supplied retention period covering audit_at |
| case_308 | 5 | INCOMPLETE / 3 | security_service/audit_record_3221: rule_12: no supplied retention period covering audit_at |
| case_309 | 5 | INCOMPLETE / 0 | security_service/audit_record_1945: rule_12: no supplied retention period covering audit_at |
| case_324 | 4 | INCOMPLETE / 4 | support_platform/support_7249: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_326 | 4 | INCOMPLETE / 4 | support_platform/support_305: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_331 | 4 | INCOMPLETE / 4 | support_platform/support_1403: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_354 | 5 | INCOMPLETE / 0 | security_service/audit_record_9286: rule_12: no supplied retention period covering audit_at |
| case_362 | 5 | INCOMPLETE / 0 | security_service/audit_record_8638: rule_12: no supplied retention period covering audit_at |
| case_369 | 5 | INCOMPLETE / 1 | security_service/audit_record_337: rule_12: no supplied retention period covering audit_at |
| case_383 | 5 | INCOMPLETE / 1 | account_service/account_5043: treatment decided; no admissible reading of the current state; security_service/audit_record_989: rule_12: no supplied retention period covering audit_at |
| case_390 | 5 | INCOMPLETE / 1 | account_service/account_7618: treatment decided; no admissible reading of the current state; backup_service/backup_5165: rule_14: no explicit restore control observed; legal_service/legal_hold_8049: rule_13: no supplied active legal hold with a basis; security_service/audit_record_101: rule_12: no supplied retention period covering audit_at; support_platform/support_5720: rule_05: conversation content not observed (shared-context condition undecidable); backup_service/backup_5165: process safe state shown only by inventory or not at all; integration_service/data_flow_5737: process safe state shown only by inventory or not at all |
| case_392 | 5 | INCOMPLETE / 1 | account_service/account_1718: treatment decided; no admissible reading of the current state; security_service/audit_record_7510: rule_12: no supplied retention period covering audit_at |
| case_403 | 5 | INCOMPLETE / 0 | security_service/audit_record_4733: rule_12: no supplied retention period covering audit_at |
| case_408 | 5 | INCOMPLETE / 0 | security_service/audit_record_4216: rule_12: no supplied retention period covering audit_at |
| case_409 | 5 | INCOMPLETE / 0 | security_service/audit_record_2559: rule_12: no supplied retention period covering audit_at |
| case_411 | 5 | INCOMPLETE / 0 | security_service/audit_record_4330: rule_12: no supplied retention period covering audit_at |
| case_412 | 5 | INCOMPLETE / 0 | security_service/audit_record_5637: rule_12: no supplied retention period covering audit_at |
| case_456 | 5 | INCOMPLETE / 0 | security_service/audit_record_8176: rule_12: no supplied retention period covering audit_at |
| case_457 | 5 | INCOMPLETE / 0 | security_service/audit_record_1171: rule_12: no supplied retention period covering audit_at |
| case_458 | 5 | INCOMPLETE / 0 | security_service/audit_record_6750: rule_12: no supplied retention period covering audit_at |
| case_462 | 5 | INCOMPLETE / 0 | security_service/audit_record_641: rule_12: no supplied retention period covering audit_at |
| case_480 | 5 | INCOMPLETE / 3 | security_service/audit_record_7742: rule_12: no supplied retention period covering audit_at |
| case_484 | 4 | INCOMPLETE / 0 | support_platform/support_7973: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_506 | 5 | INCOMPLETE / 0 | security_service/audit_record_1361: rule_12: no supplied retention period covering audit_at |
| case_512 | 5 | INCOMPLETE / 0 | security_service/audit_record_4219: rule_12: no supplied retention period covering audit_at |
| case_516 | 5 | INCOMPLETE / 1 | security_service/audit_record_3777: rule_12: no supplied retention period covering audit_at |
| case_520 | 5 | INCOMPLETE / 1 | security_service/audit_record_9504: rule_12: no supplied retention period covering audit_at; support_platform/support_9251: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_521 | 5 | INCOMPLETE / 1 | security_service/audit_record_3567: rule_12: no supplied retention period covering audit_at |
| case_522 | 5 | INCOMPLETE / 1 | security_service/audit_record_5513: rule_12: no supplied retention period covering audit_at; support_platform/support_8538: rule_05: conversation content not observed (shared-context condition undecidable) |
| case_543 | 5 | INCOMPLETE / 1 | security_service/audit_record_6244: rule_12: no supplied retention period covering audit_at |
| case_545 | 5 | INCOMPLETE / 1 | security_service/audit_record_5041: rule_12: no supplied retention period covering audit_at |
| case_547 | 5 | INCOMPLETE / 1 | security_service/audit_record_7352: rule_12: no supplied retention period covering audit_at |
| case_549 | 5 | INCOMPLETE / 1 | security_service/audit_record_1491: rule_12: no supplied retention period covering audit_at |
