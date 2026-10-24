# M5 – Policy engine – Comparison Report
Date / base commit: 2026-10-24 / branch `feature/m5-policy-engine` from verified `main`
`8ba83559d8a64024f57a1511bf47aa18ddd0233e` (M4 merged). Codex's unpublished local M5 branch was not
reachable, so M5 was implemented fresh on top of the M4 baseline; M0–M4 code is unchanged.

## 1. May reference technique
- Repo + commit: leerenjie @ `94ed9d6e93b566b1b22c30b910da8319448298ff`
- Source: `code/decider.py:87-166`, `code/policy/risk.yaml` (as recorded in `WINNER_BENCHMARK.md`; the
  benchmark clone is not in this checkout, so line ranges were not re-read for this report).
- What it does: `decide()` is a pure, LLM-free function: forced-escalation precedence, then confidence
  gates, then a default, with domain policy declared in YAML.

## 2. Our implementation
- Files: `code/policy/{rules,categories,conditions,engine,unknowns,main,reports}.py`,
  `code/policy/category_map.json`, `code/policy/condition_bindings.json`, `code/policy/tests/test_policy.py`,
  `code/evaluation/m5_metrics.py` (evaluation only; reads sample gold).
- `rules.py` loads and validates `deletion_rules.csv` at runtime (columns, actions, duplicate IDs and
  categories fail loudly). Rule text and actions exist only in the CSV.
- `categories.py` maps each subject-linked record to a policy category from declarative signals ranked
  explicit label > collection/table > record fields > readback event > system+resource prefix.
  Conflicting signals at the winning rank are AMBIGUOUS; no signal is UNMAPPED. Connector records are
  process resources deferred to M6.
- `conditions.py` holds eight three-valued predicates. Each is bound to a CSV condition by the SHA-256
  of its normalised wording, so changing the wording unbinds it (UNKNOWN) instead of reusing a stale
  meaning. A FALSE requires observed evidence: anonymity needs retained analytic content plus explicit
  null identifier columns; a support message is FALSE only when its content was read and has no
  order/agent/support context. Retention and legal-hold terms are compared with `audit_at`
  (inclusive), read from any same-system observation of the same resource captured by the cutoff that
  does not name a different person, and from document blocks that name the resource.
- `engine.py` derives the effective action (`on_false`: TARGET_SATISFIED for identifiability
  conditions, DEFAULT_ERASURE for exemptions such as retention, UNRESOLVED where no rule decides),
  computes exposed identifier fields (including identifiers inside free text such as
  `message_text`), and returns COMPLIANT / VIOLATION / UNRESOLVED / DEFERRED_M6 with the contract
  step templates. Stable internal references are permitted on tombstones and support messages;
  analytics may keep none. Backups keep RETAIN and carry a separate restore obligation
  (RESTORE_ENABLED → report/block/verify; RESTORE_BLOCKED → verify). Copies roll up per resource with
  the worst copy deciding, so primary ABSENT + replica PRESENT is a violation.
- `unknowns.py` classifies every UNKNOWN M4 latest assertion; `reports.py` writes
  `M5_UNKNOWN_ROOT_CAUSES.md` and `M5_CONDITION_COVERAGE.md` from a real run.

## 3. Improvements and differences
- Three-valued conditions instead of May's binary gates → October policy conditions often cannot be
  evaluated from the evidence, and an unknown must not become compliance or deletion.
- Condition bindings keyed by wording hash, not category → satisfies M5-1 (no rule text in code) and
  makes CSV edits safe: action edits take effect, wording edits surface as UNKNOWN.
- Field-level exposure over free text → M4 marks `support_conversations` rows and attachments as
  REDACTED when their typed identifier columns are null. In the 518-case run, 50 of the 66 such
  support-message copies still carry an email inside `message_text` (VIOLATION; 16 are genuinely
  `[REDACTED]`), and all 15 REDACTED attachment copies still exist with `uploaded_by` (remaining record
  under the DELETE rule). M5 reports these as exposed or
  remaining records rather than trusting the column-level state.
- May's YAML escalation precedence is not reused; October has no escalation concept.

## 4. Tests executed and results
| Test ID | Command | Expected | Actual | Status |
|---|---|---|---|---|
| M5-1 | `pytest code/policy/tests -k m5_1` | 15 rules loaded from CSV; no condition text in `code/policy/*.py`; changing an action in a temp CSV changes a decision, a full sample run and the CLI; edited wording becomes UNKNOWN; malformed CSVs rejected | all hold (6 `m5_1` tests + 3 malformed-CSV tests) | PASS |
| M5-2 | `pytest code/policy/tests -k m5_2` | Fixture per rule: unconditional rules PRESENT/ABSENT; conditional rules TRUE, FALSE and UNKNOWN (backup: TRUE and UNKNOWN only, since no evidence can show restore access is unblockable) | 36 fixtures, all 15 rules, 100% | PASS |
| M5-3 | `pytest code/policy/tests -k m5_3` | Participant tombstones from `customer_data_snapshot_bundle_*.json`: `subject_reference` kept; non-null name/email/phone/email_hash → `REPORT_EXPOSED_PII` + `REDACT_RECORD` + `VERIFY_RECORD_REDACTED`; all-null → `VERIFY_RECORD_REDACTED` only | both branches pass | PASS |
| M5-4 | `pytest code/policy/tests -k m5_4` (518 + 32 runs) | 0 DELETE steps on RETAIN categories; compliant retained records get `VERIFY_RECORD_PRESENT` (backups: restore verification) | 0 DELETE steps; property holds | PASS |
| M5-5 | `python3 code/evaluation/m5_metrics.py` | Dev status accuracy and step F1 reported; target ≥ 0.80 step F1 on dev | reported below; step F1 0.329 | **FAIL (target)** |
| Safety | `pytest code/policy/tests` | UNKNOWN states and unmapped categories never COMPLIANT (full run); attribute evidence after cutoff or naming another person ignored; inclusive retention boundary; document retention term; replica rollup; deterministic run | all hold | PASS |
| Regression | `/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests code/identity/tests code/intent/tests code/state/tests code/policy/tests` | M0–M5 green | **277 passed** (217 M0–M4 + 60 M5), 0 failed/skipped | PASS |
| Determinism | two runs of `python3 code/policy/main.py` | identical bytes | SHA-256 `ea3b55c9a36296a55443216b2a5806ee3590c0eb135a38e39880a4ad7a24dffc` both times | PASS |

### Development metrics (first 22 samples; holdout not used for tuning)
These come from `m5_metrics.py`, which turns policy decisions into a **provisional** steps array:
no M6 flows, no M7 ordering hook or citation guard, and an UNRESOLVED resource contributes no steps
and can never make a case COMPLETE (such cases default to INCOMPLETE).

| Split | Status acc. | Step P | Step R | Step F1 | Seq. acc. | Field acc. | Policy-scope F1 (flow steps removed) |
|---|---|---|---|---|---|---|---|
| dev (22) | 18/22 = 0.818 | 0.960 | 0.198 | **0.329** | 0.045 | 0.958 | 0.358 |
| holdout (10, report only) | 5/10 = 0.500 | 1.000 | 0.500 | 0.667 | 0.000 | 0.917 | 0.727 |

Status accuracy needs reading with care. On dev only **5** cases are decided by evidence (4 with a
violation, 1 fully compliant), and all 5 match. The other **17** are UNRESOLVED and default to
INCOMPLETE; 13 of those happen to match the sample answer. Step precision is high (one extra step,
caused by an M2/M4 correlation that links a second account, not by policy); recall is low because most
expected resources are either not linked by M2/M4 at all or have UNKNOWN M4 states.

A counterfactual that treats security audit records with no supplied retention term as retained
(evaluation-only, not the engine's behaviour) gives dev step F1 0.395 and status 17/22, so the
retention reading is not the main gap.

Final step-level F1 for the submission is **not measurable until M6–M7** exist.

## 5. UNKNOWN root causes (365 latest assertions)
Full tables: `M5_UNKNOWN_ROOT_CAUSES.md`. Primary causes: operational claims without readbacks
**229** (272 contributing), missing field-level state **96**, unsupported source scope **38**,
timestamp anomalies **2**, insufficient identity attribution **0**, conflicting facts **0**.
**326** are relevant to a policy or flow obligation (309 mapped to a rule, 17 data flows for M6),
324 of them in deletion-authorising requests; 39 have no policy category.
- The 38 unsupported-scope rows all come from one pipe-delimited log (`time | level | service |
  trace | event | key=value…`). M1's pipe parser assigns columns as
  `event_time|system_id|resource_id|data_category|state`, so the level becomes the system and the real
  `resource_id=` key is never parsed. This is an M1 defect to fix in a reviewed correction.
- Most "missing field-level state" rows are snapshot JSON records with fields but no M4 state rule
  for that shape (security audit events with only `subject_reference`, support conversations, null
  analytics profiles) and completed readbacks without row/HTTP fields. M5 does not reinterpret them;
  an M4 correction could turn many into supported states.
- No evidence was manufactured to reduce the count; M5 changes no M4 state.

## 6. Condition coverage
Full table: `M5_CONDITION_COVERAGE.md`. Over the 518 cases the engine makes 1,440 copy decisions:
COMPLIANT 199, VIOLATION 492, UNRESOLVED 589, DEFERRED_M6 160. Categories: MAPPED 1,241, PROCESS 160,
UNMAPPED 39. Observed outcomes include rule_12 (security retention) TRUE 98 / UNKNOWN 298, rule_05
(support context) TRUE 137 / UNKNOWN 51, rule_07 (analytics) TRUE 61 / UNKNOWN 19, rule_15
(tombstones) TRUE 16 with 8 exposed and 8 clean. FALSE never occurs in the participant data for the
conditional rules; FALSE paths are covered by fixtures only. Rules 02, 04, 08, 10 (eval) and 11 have
no mapped records in the 518-case run.

## 7. Known limitations
- Dev step F1 0.329 is far below the 0.80 target. The gap is upstream (unlinked resources, UNKNOWN
  M4 states) and in M6/M7 scope (flows, always-verified account absence), not tunable in M5 without
  answer-shaped rules.
- Security audit records usually carry no retention term; under the strict reading they are
  UNRESOLVED (never deleted). Whether a sealed audit record without a term should default to retained
  is a policy decision for the project owner, not something M5 assumes.
- `on_false` choices (DEFAULT_ERASURE for expired retention/hold or support messages without shared
  context, UNRESOLVED for shared attachments, tombstones of non-deleted accounts and backups) are
  documented interpretations in `condition_bindings.json`, untested against participant FALSE cases.
- Category signals for support records whose content is not observed (e.g. a replica contact index
  or a PII-scan line) stay UNMAPPED; `support_replica` is not normalised to `support_platform` (M7).
- PDF retention is read only from document blocks naming the resource; the legal register's
  user-level rows are not linked to `legal_hold_*` resources.
- Provisional synthesis in `m5_metrics.py` is evaluation scaffolding, not the M7 synthesiser.

## 8. Recommendation: PASS for M5-1 to M5-4, FAIL on the M5-5 F1 target
M5-1, M5-2, M5-3 and M5-4 pass, the full M0–M5 suite is green (277) and runs are deterministic. M5-5's
reporting requirement is met, but its ≥ 0.80 dev step-F1 target is not (0.329). Per the instruction to
stop after M5, M6/M7 were not started; the root-cause report identifies the M1 pipe-log parser and the
M4 field-level gaps as the highest-yield fixes before or alongside M6.

---

# Rev 2 – independent-review corrections (supersedes the numbers above)
Base: reviewed commit `0570185e48bc622ab3ddd40c84150797d2041922`. Sections 1–8 above are kept unchanged
as the rev 1 record; rev 1 generated reports are preserved as `M5_UNKNOWN_ROOT_CAUSES_rev1.md` and
`M5_CONDITION_COVERAGE_rev1.md`, and the current files are regenerated. The security-retention decision
is unchanged: a record with no supplied retention period stays condition UNKNOWN / UNRESOLVED.

## R1. Cross-customer evidence (priority 1)
Review finding: `_dossier()` added any same-ID observation unless `_identity_conflict()` saw a
conflicting stable reference; plain email, phone and hash fields were not checked, and unattributed
records could supply a retention date or category signal.

Correction (`code/policy/conditions.py: identity_claims, Subject.attribution`, `engine.py: _attribution`):
- Every explicit identifier a record names is collected: emails anywhere (including free text), user
  references, phone fields and phone-shaped values, hash fields and `correlation_key` hashes.
- A same-ID observation that is not already subject-linked by M2/M4 is used only when it names at least
  one identifier and **every** named identifier belongs to the subject's cutoff-time identity view
  (`IdentityGraph.at`). FOREIGN and UNATTRIBUTED observations are dropped, whatever their topology.
- M4 assertions marked `mixed_context` no longer enter the dossier.
- A PDF retention term counts only if its own document block names the subject and nobody else.

Tests (15 new): different email / phone / email hash / user reference / mixed identities / foreign
free text on a same-ID record → ignored; same subject via user ref, case-folded email, reformatted phone
or hash → used and cited; unattributed retention date → ignored; replica copy naming the subject used,
replica naming another user ignored; historical email known by the cutoff attributes, the same email
absent from the cutoff view does not, evidence captured after `audit_at` never counts; a decoy record
with `email_opt_in` for another person leaves category, rule, condition, action, compliance and
obligations identical; a document term for another subject is ignored.
Effect on participant data: **0** of 1,440 decisions changed, so no rev 1 decision relied on
contaminated evidence; the path is now closed.

## R2. M1 pipe-delimited log parser (priority 2)
`parse_lines()` now recognises `time | LEVEL | service | trace | event | key=value…` when the second
column is a log severity. It records `level`, `service`, `trace_id` and `event`, parses quoted
key=value attributes (without letting them overwrite those structural columns), keeps the original line
in `text`, and leaves the handover format (`time | system | resource | category | state | ids`) and
all other formats unchanged. `PARSER_VERSION` is `m1-v2`, so cached parses are invalidated.
Tests: one synthetic fixture (including a spoofed `level=` attribute) and one participant test over
both operations-stream logs (no severity as system; every line with `resource_id=` gets that ID).

Impact on the 38 malformed assertions (all from `evidence_48`, 10 cases): they disappear and the same
lines now yield **34** correctly keyed physical copies, of which **20** are source-supported (9 ABSENT
from completed 404/zero-row profile lookups, 11 PRESENT from completed one-row audit reads) and **14**
stay UNKNOWN because they are claims (index hits, PII scans, heartbeats). The second operations-stream
log (`evidence_21`) contributes no latest assertion before or after. The 32 sample cases are unchanged
by this step. Ingestion coverage remains 94/94 files (83 parsed, 11 images `needs_multimodal`).

## R3. M4 field-level state gaps (priority 3)
All 96 "missing field-level state" assertions came from four observed shapes:

| Shape | Copies | Content |
|---|---|---|
| completed `support_ticket_read_completed` log readback | 33 | returned `customer_reference`, `requester_*` fields; no rows/HTTP keys |
| completed `analytics_profile_read_completed` log readback | 8 | returned `audience_cohort`, email/phone/hash fields |
| JSON export/bundle security audit records | 42 | `subject_reference`, `event_code`/`event_name`, retention or integrity seal |
| JSON support messages / attachment / legal hold | 13 | message or file fields, hold term |

Two narrow rules were added to `code/state/engine.py`:
- A completed READBACK event with matching `resource_id`, matching `service`, an event time and no row
  or HTTP key, which returned at least one non-null record field, is a readback of that record.
- A JSON record (not a `result` claim, not a status/row readback) with at least one non-null field of
  its own is an observed record.
For both, identifiers present → PRESENT; account/support rows without direct identifiers → REDACTED
(same as the existing SQL rule); analytics without identifiers → ANONYMIZED only with retained analytic
content, else UNKNOWN; other records → PRESENT. Envelope-only lines, `_started` events, service or
resource mismatches, missing event times, all-null field sets, `result: FOUND` claims and worker
results stay UNKNOWN (7 new M4 tests). Timestamp quarantine runs afterwards, so both anomalies stay
quarantined.

Result: all 96 became supported (PRESENT 73, REDACTED 23); **no previously supported latest state
changed**; replica drift, opposing-fact conflicts and cutoff violations remain 0/0/0. M5 still applies
its own field checks: e.g. REDACTED support rows whose `message_text` contains an email are violations,
and the newly PRESENT audit records without a retention term remain UNRESOLVED.

## R4. Re-evaluation
| Measure | Rev 1 | Rev 2 |
|---|---|---|
| Latest physical copies (518 cases) | 1,440 | 1,436 |
| Source-supported / UNKNOWN | 1,075 / 365 | 1,191 / 245 |
| UNKNOWN causes | claims 229, field gaps 96, scope 38, timestamp 2 | claims 243, timestamp 2 |
| Policy-relevant UNKNOWN (deletion requests) | 326 (324) | 240 (238) |
| Copy decisions COMPLIANT / VIOLATION / UNRESOLVED / DEFERRED_M6 | 199 / 492 / 589 / 160 | 250 / 504 / 519 / 163 |
| Category MAPPED / PROCESS / UNMAPPED | 1,241 / 160 / 39 | 1,268 / 163 / 5 |
| rule_12 TRUE / UNKNOWN | 98 / 298 | 98 / 308 |
| DELETE steps on RETAIN categories | 0 | 0 |
| M4 DELETE-all provisional dev status | 14/22 | 13/22 |
| M5 dev status (evidence-decided correct) | 18/22 (5/5) | 19/22 (7/7) |
| M5 dev step P / R / **F1** | 0.960 / 0.198 / **0.329** | 0.966 / 0.231 / **0.373** |
| M5 dev policy-scope F1 | 0.358 | 0.406 |
| M5 dev sequence / field accuracy | 0.045 / 0.958 | 0.045 / 0.944 |
| Retention counterfactual dev F1 (what-if only) | 0.395 | 0.436 |
| Holdout step F1 (report only, not tuned) | 0.667 | 0.759 |
| M0–M5 tests | 277 passed | **301 passed** |

Test count: `pytest code/evaluation/tests code/ingest/tests code/identity/tests code/intent/tests
code/state/tests code/policy/tests` → **301 passed**, 0 failed/skipped (rev 1 suite 277 + 2 M1 parser
tests + 7 M4 state tests + 15 M5 attribution tests, counting parametrised cases). Identity/retrieval safety
tests (M2 decoys, correlation safety, recall accounting) all pass unchanged. Two consecutive 518-case
policy runs are byte-identical (SHA-256 `29a0089281eb95a744219bf6d6cc7901a6adb6699a550657cf305ffa08c784df`);
two state runs likewise (`fa6bdc8019f7323cc86d3f51667c75943aaf1aa41c87dc487e6e3f5576e8247d`).

## R5. M5-5 and the remaining gap
The 0.80 dev step-F1 target is retained and still **not met (0.373)**. On dev, 15 of 22 cases still
contain at least one UNRESOLVED resource. The remaining gap is dominated by: (a) expected resources that
M2/M4 never link to the subject (e.g. the always-verified account absence when no account evidence is
retrieved); (b) 243 operational claims with no readback; (c) security audit records without a supplied
retention period, deliberately UNRESOLVED; and (d) data-flow findings/remediation/verification, which
belong to M6, and final ordering/citation rules in M7. None of these is addressed by lowering the
metric, hardcoding answers or tuning on the holdout.

## R6. Recommendation (rev 2)
M5-1 to M5-4 PASS; the review's attribution defect, the M1 pipe-log defect and the M4 field-level gaps
are corrected with regression tests; M5-5 remains FAIL against its 0.80 target. Stopping for
independent review; M6 not started, no PR opened.

---

# Rev 3 – attribution and temporal-evidence safeguards
Base: reviewed commit `a5c4e939c6372ebc0d3d59bf3b4f88b184ab955d`. Rev 1 and Rev 2 sections above are kept.

## T1. Already-linked M2/M4 observations (`code/policy/engine.py: _dossier, decide_copy`)
Rev 2 re-checked only *additional* same-ID observations. Now every observation entering the policy
dossier, including those already linked by M2/M4, is re-checked against every identifier it names
(emails including free text, phones, email hashes, user references) and the subject's cutoff-time
identity view:
- all identifiers belong to the subject → usable;
- any identifier belongs to someone else, or M4 marked the link `mixed_context` → **contradictory**:
  the observation is kept as evidence in `attribution_conflicts`, never used, and the copy's decision
  becomes UNRESOLVED with no obligations (never COMPLIANT, never a DELETE/REDACT plan);
- no identifiers at all → usable only when M2/M4 joined it through an explicit trace correlation
  (`correlated`); otherwise ignored (an identifier-free record has no own-record attribution).
The state-establishing record itself is subject to the same rule, and category signals now come only
from usable observations plus the assertion's own system/resource prefix.

## T2. Temporal admissibility
One check (`_admissible_time`) now guards both dossier loops and PDF document terms: evidence is
inadmissible when `captured_at` > `audit_at`, its record or event time is after `audit_at` or after
its own capture, or M1 quarantined it (`record_time_after_manifest_capture`, passed in from ingestion).

## T3. Tests (11 new; 312 total)
Contradictory linked records (subject email + foreign phone, subject user ID + foreign email hash, two
customers in one record) → UNRESOLVED with the conflict cited; `mixed_context` link → UNRESOLVED;
historical email in the cutoff view → COMPLIANT, the same record without that history → UNRESOLVED;
identifier-free record → used via `correlated` trace join, ignored via `context`/`direct`; a quarantined
linked record with a favourable retention date stays UNKNOWN (not COMPLIANT); late record time and late
event time are rejected for linked and additional records; a post-cutoff capture is rejected even when
linked; both participant M1 anomalies are excluded with and without the quarantine set (neither is
cited, neither yields COMPLIANT). The rev 2 attachment FALSE fixture is now reached through the
predicate directly, because in the engine a linked attachment naming another uploader is a
contradictory attribution and stays UNRESOLVED first.

## T4. Real-data effect and non-regression
On the 518 cases, linked observations entering M5 are: subject-attributed 1,827 (direct 1,409,
direct_verified 172, context 246), identifier-free but trace-correlated 97, temporally inadmissible 2
(the two M1 anomalies, whose assertions were already UNKNOWN). None is contradictory. Consequently
**0 of 1,436 decisions changed**; the safeguards close paths that the participant data does not
exercise today. The full 518-case policy JSON is byte-stable across runs (SHA-256
`cae487cdcf2a2ee0efcf5c14ba04b5ec4e3aaa36d6ab715fe76ab77a1d5f2f8e`; it differs from rev 2 only by the
new `attribution_conflicts` fields and summary count). The M4 state output is unchanged from rev 2
(`fa6bdc80…e8247d`), so the evidence_48 parsing, its 20 recovered states and the 96 structured-record
states are preserved. Regenerated `M5_UNKNOWN_ROOT_CAUSES.md` and `M5_CONDITION_COVERAGE.md` are
byte-identical to rev 2, and `m5_metrics.py` output is identical: dev status 19/22, dev step F1
**0.373** (target 0.80 retained, unmet), holdout reported only. Strict boolean parsing, identifier
conflict checks and the security-retention UNKNOWN decision are unchanged.

## T5. Gates (rev 3)
| Gate | Result |
|---|---|
| M5-1 CSV-driven rules | PASS |
| M5-2 per-rule condition fixtures | PASS |
| M5-3 tombstone redaction (participant bundles) | PASS |
| M5-4 no DELETE on RETAIN categories (0 in 518 + 32) | PASS |
| M5-5 dev step F1 ≥ 0.80 | **FAIL** (0.373); explicitly unmet integration target pending M6/M7 |
| Attribution safety (linked + additional records) | PASS (tests) |
| Temporal admissibility (incl. both M1 anomalies) | PASS (tests) |
| M0–M5 regression | **312 passed**, 0 failed/skipped |
