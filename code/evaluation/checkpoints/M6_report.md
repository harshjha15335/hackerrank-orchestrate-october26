# M6 – Active data flows and restore risks – Comparison Report
Date / base commit: 2026-10-24 / branch `feature/m6-flow-restore-risks` from verified `main`
`ebcd897527ffba6fe5ed411f368565ba3bad0dfa` (merge of approved M5 Rev 3 `70517bc3`, PR #2).

## 1. May reference technique
- None. `DEVELOPMENT_CHECKPOINTS.md` lists M6 as a gap: no May repository models data-flow or
  restore-path state. The nearest analogue remains trenton's refusal to trust a claimed workflow
  outcome (`code/agent/pipeline.py:107-118`, as recorded in `WINNER_BENCHMARK.md`; not re-read here),
  which M6 applies to `CHECK_DATA_FLOW`, `DISABLE_DATA_FLOW`, `BLOCK_RESTORE` and
  `CHECK_RESTORE_ACCESS` activity rows.

## 2. Our implementation
- Files: `code/flow/{evidence,engine,dependencies,main,reports}.py`, `code/flow/README.md`,
  `code/flow/tests/test_flow.py`, `code/evaluation/m6_metrics.py` (evaluation only; reads sample gold),
  `code/evaluation/checkpoints/M6_FLOW_DIAGNOSTICS.md` (generated). M1 change:
  `code/ingest/evidence.py` parser `m1-v3` (log envelopes, §3).
- `evidence.py` reads one observation of an `integration_service` `data_flow_*` or `backup_service`
  `backup_*` resource into a state and evidence class. Snapshot, readback and field-value states
  come from M4's own interpreter; M6 adds owning-service telemetry (`connector_heartbeat`,
  `connector_config_loaded`, `restore_candidate_evaluated`, `restore_authorization_completed`) and
  inventory listings (handover lines, `record_type`/`result` records, `record_lookup` logs).
  Activity rows are claims and never a state.
- `engine.py` assesses each process per case: subject ownership (direct record identifiers, or an
  identifier-free line in an explicit same-file trace that names only the subject), the M4/M5
  temporal gate, deterministic latest-reading selection, CONFLICTING for same-time disagreement or a
  same-ID record naming another person, and the contract obligation templates, each marked
  `observed` or `proposed`.
- `dependencies.py` keeps evidenced edges for M7 (recreation by sync/restore with both ends named,
  derivation events with an unnamed upstream, connector destinations, physical copies) and
  recommends process-first precedence. It does not order steps.
- `main.py` is the deterministic inspection CLI; per case it returns `flows`, `restores` (with the
  M5 retention rule and `delete_forbidden`), `dependencies`, `precedence` and
  `m4_linked_not_attributed`.

## 3. Improvements and differences
- **Asymmetric proof.** Risk (ACTIVE / RESTORE_ENABLED) may come from any non-claim reading,
  including inventory listings; a safe state needs a snapshot, readback, observed configuration or
  owning-service telemetry. Rationale: a missed active flow or restore path recreates deleted data,
  while an unproven "disabled" would let a case pass as COMPLETE. This is a judgment call; it is the
  only place M6 accepts a source class M4 rejects, and only in the risk direction.
- **Restore access is separate from retention.** Backups stay RETAIN under M5 rule_14 (58/58 restore
  assessments carry `delete_forbidden`); M6 alone decides report/block/verify. `archive_present=true`
  and a FOUND/PRESENT backup are not restore states.
- **M1 log envelopes (`m1-v3`).** Eight participant logs in four layouts (JSON-object, bracket,
  syslog, function-runtime) were stored as text without `service`, `event`, `trace_id` or, for JSON
  lines, `resource_id`. Many heartbeat and restore-evaluation lines are only in these files. After the
  fix, the 518-case run has 123 new subject-linked physical copies (M4: 34 PRESENT, 26 ABSENT,
  63 UNKNOWN; M5: 26 COMPLIANT, 4 VIOLATION, 82 UNRESOLVED, 11 DEFERRED_M6). Existing decisions
  changed: **0** of the M4 latest states and **0** of the M5 copy decisions (compared key by key
  against a run at `ebcd897`). The 32 samples are unaffected.
- **No naming inference.** Connector names such as `search_profile_indexer` are not dependencies;
  only an activity row naming both the process and the downstream record (`recreated_by_sync`, 29
  edges) or a configured `destination` field (56) links them.

## 4. Tests executed and results
| Test ID | Command | Expected | Actual | Status |
|---|---|---|---|---|
| M6-1 | `pytest code/flow/tests -k m6_1` | Snapshot timeline ACTIVE → DISABLED → ACTIVE evaluated at three cut-offs gives ACTIVE (report/disable/verify), DISABLED (verify only, cited), ACTIVE; cutoff before any evidence gives no assessment; boundary inclusive | all hold (5 tests) | PASS |
| M6-2 | `pytest code/flow/tests -k m6_2` | restore_allowed=1 → report/block/verify; =0 → `VERIFY_RESTORE_BLOCKED` only; `archive_present` only, non-boolean, missing flag and FOUND inventory → UNKNOWN with no obligations | all hold (6 tests) | PASS |
| M6-3 | `pytest code/flow/tests -k m6_3`; `python3 code/evaluation/m6_metrics.py` | Dev recall 1.0 on flow and restore steps, or every miss explained | dev 21/21 matched, 0 missed, 0 extra, evidence_id 21/21 | PASS |
| Regressions | `pytest code/flow/tests` | unrelated customer process; connector active without subject link; trace with two people; trace ID in another file; reused resource ID (CONFLICTING); decoy backup; identifier outside cutoff identity view; post-cutoff enablement; late `observed_at`; quarantine; worker claims never state; later unverified disable claim; inventory risk-not-safety; inconsistent readback; same-time disagreement; missing/misplaced process identifiers; telemetry from a non-owning service; restore telemetry vocabulary; cross-system dependency chain and precedence; post-cutoff dependency; no DELETE on backups (518 + 32); UNKNOWN/CONFLICTING carry no obligations (518); deciding readings owned and admissible (518); M4/M5 output unchanged by M6; deterministic run and CLI; no sample answer IDs in `code/flow` | all hold (44 tests in `code/flow`) | PASS |
| M1 envelopes | `pytest code/ingest/tests -k envelope` | fixture for each layout incl. spoofed envelope keys and a non-trace slot; all 8 participant envelope logs keep resource, service and event | all hold (9 tests) | PASS |
| Full suite | `python3 -m pytest -q -p no:cacheprovider code` | M0–M6 pass | **365 passed** (312 before M6 + 9 M1 + 44 M6) | PASS |
| Determinism | `python3 code/flow/main.py \| sha256sum` twice (518 cases) | identical | `e30d5394…a1bc79` both runs | PASS |

Metrics (from `m6_metrics.py`; dev tuned, holdout report-only):

| Split | Flow/restore steps expected | Predicted | Matched | Precision | Recall | evidence_id |
|---|---|---|---|---|---|---|
| dev (case_01–22) | 21 | 21 | 21 | 1.0 | 1.0 | 21/21 |
| holdout (case_23–32) | 12 | 12 | 12 | 1.0 | 1.0 | 12/12 |

Provisional combined steps (M5 policy + M6 process obligations, operation-table order, no M7
citation guard or dependency reordering):

| Split | Run | Status | Step P | Step R | Step F1 | Field acc | Sequence acc |
|---|---|---|---|---|---|---|---|
| dev | before M6 (M5 only) | 19/22 | 0.9655 | 0.2314 | 0.3733 | 0.9439 | 0.0455 |
| dev | after M6 | 19/22 | 0.9787 | 0.3802 | **0.5476** | 0.9379 | 0.0455 |
| holdout | before M6 | 9/10 | 1.0 | 0.6111 | 0.7586 | 0.9123 | 0.0 |
| holdout | after M6 | 9/10 | 1.0 | 0.7361 | 0.8480 | 0.9299 | 0.0 |

518-case assessments: data flows ACTIVE 112, DISABLED 31, UNKNOWN 2, CONFLICTING 0; restore paths
RESTORE_ENABLED 25, RESTORE_BLOCKED 31, UNKNOWN 2, CONFLICTING 0. Attribution: 193 direct, 10 trace
(203/203 source-backed; 0 ownership conflicts). All 4 UNKNOWNs are cases 41 and 390, where the only
reading is an inventory listing saying DISABLED/BLOCKED. Status counts are per case; a process can
appear in more than one case.

## 5. Changes to M0–M5 and remaining uncertainty
- M0–M5 decisions: no existing M4 state or M5 decision changed. M6 does not modify M4 states or M5
  decisions; `test_m6_does_not_change_m4_or_m5_decisions` checks the sample run.
- M4 UNKNOWN count: the reviewed 245 UNKNOWN latest states are unchanged, and the M1 envelope fix
  adds 63 newly linked UNKNOWN copies, so the 518-case M4 run now reports **308** UNKNOWN latest
  states. M6 uncertainty is reported separately (4 UNKNOWN assessments). M6 does not promote any
  M4 UNKNOWN: 35 process resources that M4 left UNKNOWN have a supported M6 assessment (28 ACTIVE,
  5 RESTORE_ENABLED, 1 DISABLED, 1 RESTORE_BLOCKED), and their M4 state stays UNKNOWN.
- M5-5 (dev step F1 ≥ 0.80): **still unmet**. Provisional dev F1 is 0.548. The flow/restore gap is
  closed on dev; the remaining recall gap is record-level (M4 UNKNOWN states and unlinked records,
  M5 UNRESOLVED retention), and sequence accuracy needs M7. These numbers stay provisional until M7
  produces real `steps_json`.

## 6. Known limitations
- Screenshots `connector_management_console_20260807.png` and `backup_restore_console_20260429.png`
  are `needs_multimodal` (M8). Any flow or restore state shown only there is missing.
- Inventory listings are accepted for risk only. If such a listing is wrong, M6 reports a false risk
  (safe direction). Cases 41 and 390 stay unresolved for the same reason.
- `derived_from_source_system` edges name only the upstream system. They are marked `system_level`,
  and M7 decides whether they may reorder steps. On this data no subject-linked record has such an
  edge, so the count is 0.
- Holdout independence is limited: the full sample answer file, holdout included, was viewed
  once at the start to locate process steps. No reading rule was added for a holdout-only
  pattern, and all 12 holdout process steps are decided by JSON field values, which M4 already
  read before M6. Still, the holdout is not a blind test for M6, and its 12/12 should be read
  as a consistency check rather than an independent estimate.

## 7. Recommendation: PASS
Justification: M6-1, M6-2 and M6-3 pass, with dev recall 1.0 and no misses to explain. All 44 M6
regressions pass, and the M0–M6 suite has 365 passing tests. M6 keeps provenance, ownership and
temporal safety, and adds no change to earlier decisions. The original M5-5 target (0.80) is still
unmet at provisional dev F1 0.548. M7 owns step synthesis, ordering and citations.

---

## Rev 2 – Trace-anchor cutoff correction (review of `dfc34ba`)

### T1. Defect
`FlowContext.trace_claims` merged the identifiers of every line in a same-file trace before the
case cutoff was applied, and `attribution()` used that merged set to attribute identifier-free
process readings. A trace anchor stamped after `audit_at`, stamped after its own manifest capture
or quarantined by M1 could therefore establish ownership of an earlier heartbeat. An inadmissible
foreign anchor could also contest a valid pre-cutoff association. M2's trace expansion in
`identity/retrieval.py` had the same gap: it checked each emitted hit's capture time, but not the
event/record times or quarantine status of the anchors or of the lines that make a group ambiguous.

### T2. Fix
- `code/flow/engine.py`: trace groups keep each line with its identifiers. The new
  `trace_identity()` unions the identifiers of only those lines that pass the M4/M5 temporal gate at
  the current case's cutoff: manifest capture ≤ `audit_at`, event and record time ≤ `audit_at` and
  ≤ capture, and not M1-quarantined. `attribution()` uses it. Grouping is still exact
  `(evidence_id, trace_id)`, ownership is still checked against the cutoff-time identity view, and
  any admissible foreign identifier still rejects the join.
- `code/identity/retrieval.py`: `EvidenceIndex` takes the M1 anomaly set. Before a trace group can
  anchor, or be found ambiguous, it is reduced to its admissible lines at the cutoff.
  `state/main.py`, `policy/main.py` and `flow/main.py` pass the anomaly set.

### T3. Regressions (13 new)
| # | Scenario | Test | Result |
|---|---|---|---|
| 1 | Earlier identifier-free heartbeat, anchor stamped after `audit_at` | `test_post_cutoff_trace_anchor_cannot_attribute_earlier_heartbeat` (+ pre-cutoff control) | no attribution |
| 2 | Anchor stamped after its manifest capture | `test_trace_anchor_stamped_after_its_capture_is_not_evidence` | no attribution |
| 3 | Quarantined anchor | `test_quarantined_trace_anchor_cannot_attribute` | no attribution |
| 4 | Valid subject anchor + later inadmissible foreign anchor | `test_inadmissible_foreign_anchor_keeps_valid_trace_attribution` | association kept |
| 5 | Admissible subject and foreign anchors in one trace | `test_admissible_subject_and_foreign_anchors_are_ambiguous` | rejected |
| 6 | Same trace ID in another file | `test_trace_anchor_in_another_file_never_joins` (and the existing `test_same_trace_id_in_another_file_is_not_a_join`) | never joins |
| 7 | Historical email valid at cutoff (real `IdentityGraph` over a fixture audit log) | `test_historical_email_at_cutoff_joins_trace` | joins |
| 8 | Email acquired after cutoff | `test_email_acquired_after_cutoff_does_not_join_trace` | no join |
| 9 | Participant trace attributions | `test_participant_trace_attributions_are_unchanged` (518 + 32) | 10 trace attributions, all deciding readings admissible |
| M2 | Post-cutoff, after-capture and quarantined anchors; inadmissible foreign anchor does not block | 4 tests in `code/identity/tests/test_correlation_safety.py` | all hold |

Full suite: `python3 -m pytest -q -p no:cacheprovider code` → **378 passed** (365 + 13).

### T4. Effect on participant data
Compared key by key against runs at `dfc34ba` on all 518 cases:
- M4 latest states: 0 changed, 0 added, 0 removed (UNKNOWN stays 308).
- M5 copy decisions: 0 changed.
- M6 assessments: 0 changed status, attribution, deciding evidence or obligations. Flows are still
  ACTIVE 112, DISABLED 31, UNKNOWN 2; restores are still RESTORE_ENABLED 25, RESTORE_BLOCKED 31,
  UNKNOWN 2; attribution is still 193 direct and 10 trace.
- 16 diagnostic readings changed their `attribution` label from `trace` to `none`. They are already
  inadmissible readings (`admissible: false`, in files captured after that case's cutoff, e.g.
  `evidence_06`, `evidence_44`), so they never decided anything. Their anchors are now inadmissible
  too.
- Dev flow/restore steps are still 21/21 and holdout 12/12. Provisional dev step F1 is still 0.548
  and holdout 0.848, so M5-5 (0.80) is still unmet.
- Determinism: two 518-case `flow/main.py` runs both give `18293be6…4909fa8b`. The digest differs
  from Rev 1 only because of the 16 diagnostic labels above.

As the review expected, the vulnerability was source-level. In this dataset an anchor's event time
never falls between its file's capture and a case cutoff, so no case was affected.

### T5. Recommendation: PASS (pending independent review)
Every trace anchor that creates or contests ownership is now evidence at the case cutoff, and the
13 regressions cover the requested scenarios. No decision on participant data changed, and the
contract constraints still hold: no post-cutoff evidence, no claim promoted to proof, no DELETE on
retained backups, and no sample gold in production code. `dataset/` is untouched and there is no
root `output.csv`.
