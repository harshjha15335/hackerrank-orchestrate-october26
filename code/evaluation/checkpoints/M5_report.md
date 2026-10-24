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
