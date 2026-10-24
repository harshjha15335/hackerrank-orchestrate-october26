# M7 – Step synthesis, ordering and evidence-citation guard – Comparison Report
Date / base commit: 2026-10-24 / branch `feature/m7-step-synthesis` from verified `main`
`0e046f108f39ec24cde81abd9f932a149efeaace`. That is the merge of approved M6 Rev 2 `89ba3bfa` via
PR #3, which Harsh approved on 2026-10-24. Remote `main` contains `89ba3bfa`, checked with
`git merge-base --is-ancestor`.

## 1. May reference technique
- saai citation guard, `code/agent/middleware/citation_guard.py:15-72` @ `fadb4f24`, as recorded in
  `WINNER_BENCHMARK.md` (not re-read here). A cited path survives only if the agent actually read it
  that turn. Unread citations are dropped and logged.
- leerenjie tiered verifier, `code/verifier.py`, as listed in `DEVELOPMENT_CHECKPOINTS.md`. It checks
  a drafted answer against cheaper deterministic checks before accepting it.

## 2. Our implementation
- Files: `code/synthesis/{main,synthesizer,citations,ordering,risk}.py`, `code/synthesis/README.md`,
  `code/synthesis/tests/test_synthesis.py` (46 tests), and `code/evaluation/m7_metrics.py`
  (evaluation only; reads the sample answers).
- Small changes to earlier stages:
  - `code/state/engine.py` `system_for`: a record with no system takes the system named by its
    file's manifest origin when that origin is a known owning system, plus one snapshot table
    alias (`search_documents_*` → `search_service`).
  - `code/evaluation/contract.py` `validate_rows(..., allow_unproven_incomplete=False)`.
- `synthesis/main.py` is the offline inference entry point. It runs M1–M6 through the existing
  modules and synthesizes all 518 (or 32) rows into an explicit temporary CSV. It refuses root
  `output.csv` and `dataset/`. `--case <id> --explain` prints one case's row, its diagnostics and
  every citation check.
- `synthesizer.py` derives case status and steps from typed M5/M6 decisions:
  - VIOLATION record → its action template;
  - COMPLIANT record → its verification;
  - UNRESOLVED record with a decided treatment → its future verification only;
  - undecided or contested record → no step, kept in diagnostics;
  - M6 process → its M6 obligations; UNKNOWN or CONFLICTING → none.

  A case is COMPLETE only when it has at least one resource or process, every copy is COMPLIANT,
  every process is proven safe, nothing is unresolved, and every verification citation passes the
  guard. An empty case is never COMPLETE.
- `citations.py` re-reads every cited observation by its evidence ID and locator, and checks seven
  things:
  1. the ID exists among participant files, activity or audit rows;
  2. its time is at or before `audit_at`;
  3. the M4/M5 temporal gate and the M1 quarantine;
  4. it names the step's resource and system;
  5. it is not a workflow or activity claim;
  6. it names only the subject, directly or through an admissible same-file trace;
  7. the state it re-derives itself supports the operation.

  It does not trust upstream labels. A rejected finding falls back to a future check, and a
  rejected COMPLETE verification makes the case INCOMPLETE.
- `ordering.py` sorts canonically (phase, operation-table order, `system_id`, `resource_id`) and adds
  the §6.5 dependency hook (see §3), then renumbers.
- `risk.py` adds two evidence-grounded extensions (see §3). It never modifies M4 states or M5
  decisions; it overlays copies for M7 only.

## 3. Improvements, differences and judgment calls for review
- **Future verification for decided-but-unproven records.** An INCOMPLETE case lists the checks that
  must pass after remediation. When policy fixes the target state (for example rule_01 DELETE →
  `VERIFY_RECORD_ABSENT`) and only the current state is UNKNOWN, M7 emits that future check with an
  empty `evidence_id`. It never emits a finding or remediation for it. This is the largest dev gain.
- **Risk-direction record readings (judgment call).** These apply M6's approved asymmetric-proof rule
  to records. The following can show a record is still present or exposed:
  - owning-service telemetry: `index_query_completed result=hit`, `*_lookup_completed` /
    `*_query_completed rows=1`, export `available=true`, and `*_pii_scan` /
    `analytics_identity_scan` with `detector=direct_identifier`;
  - inventory listings saying FOUND / PRESENT / IDENTIFIABLE;
  - a document exported by the owning system that is the record itself.

  NOT_FOUND, `result=miss`, `rows=0` and `available=false` cancel an older risk but never prove
  compliance. Only UNRESOLVED copies with an UNKNOWN M4 state can change, and only to VIOLATION. An
  exposure reading can also make `still_attributable` TRUE, and a matched email can make
  `contains_email_address` TRUE, because those predicates are exactly the exposure. RETAIN records
  and `within_retention_period` are never decided here, so security audit records with no supplied
  retention period stay UNRESOLVED, as Harsh decided. On the 518 cases, 142 copies change:
  - 122 DELETE copies from a hit or FOUND reading (84 telemetry, 38 inventory);
  - 20 ANONYMIZE copies from an exposure reading (11 inventory IDENTIFIABLE, 9 identity scans).

  The `*_lookup_completed rows=1` form was added after the dev error analysis (dev `analytics_9914`).
  It is generic, but it has exactly one participant occurrence.
- **System-less records (M4).** Eight observations in four files had a resource but no system, so
  M4 dropped them (`evidence_56/57/58/59`). The manifest origin (`analytics_platform`,
  `support_platform`, `export_service`) and the `search_documents_*` table now name their owning
  system. Effect, compared key by key: 518 cases, 0 M4/M5/M6 changes; samples, +3 linked copies, 0
  changed.
- **Referenced source records.** A record that names only the subject and carries
  `source_resource_id` states which record it was derived from. That upstream record is added with
  an UNKNOWN state. Its system comes from admissible activity rows that agree on it. A
  `record_level` dependency edge is kept for the hook. Participant data has one such field
  (`evidence_57`), so this gives one sample link and none in the 518 cases.
- **Dependency hook vs canonical order.** `problem_statement.md` fixes the order as phase, then
  operation table, then `system_id`/`resource_id`. The operation table already puts
  `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` before every record remediation, so the "stop recreation
  first" rule never needs an exception. The hook reorders only same-operation remediation pairs on
  a `record_level` downstream→source edge. System-level edges (upstream record unnamed), names and
  event proximity never reorder anything. A cross-operation conflict is reported, not applied,
  because it would break the official phase/operation order. Contradictory edges (a cycle) keep
  canonical order and are reported. Participant data: 0 reorders, 0 conflicts and 0 cycles on both
  the 518 cases and the samples. The only record-level edge (case_06) has no remediation at the
  source end.
- **INCOMPLETE without a provable finding.** Some cases have no linked resource at all (10 of 518),
  or every gap is an undecided treatment. They are INCOMPLETE with either no steps (40) or future
  verification only (40 more; 80 without a finding in total). No uncertainty operation is invented.
  The M0 validator's "INCOMPLETE needs all three phases" rule was inferred from the samples, so it
  stays the default. `allow_unproven_incomplete=True` accepts these shapes in M7 output. In the
  strict M0 mode, the 518-case file has 120 errors in those 80 rows. These rows are a
  scoring-format risk to settle in M9/M10.

## 4. Tests executed and results
| Test ID | Command | Expected | Actual | Status |
|---|---|---|---|---|
| M7-1 | `pytest code/synthesis -k m7_1`; `m7_metrics.py` `m7_1_serialization` | Re-emitting the canonical keys of the 32 sample outputs, after two different scrambles, is sequence-identical; production code never reads the answers | 32/32 identical; no answer file or answer ID in `code/synthesis` | PASS |
| M7-2 | `pytest code/synthesis -k m7_2` | Downstream-before-source reorders only the evidenced pair; process-before-record is canonical; system-level or satisfied edges never reorder; cross-operation conflict reported; contradictory edges fall back; chained edges; samples stay canonical; the participant edge is record-level and cited | all hold (8 tests); 0 reorders on 518 and 32 | PASS |
| M7-3 | `pytest code/synthesis -k m7_3`; `main.py --summary` | 100% validity of nonempty citations. Adversarial rejects: wrong subject, mixed subject/foreign, wrong resource, wrong system, late capture, late record time, unsupported status both ways, workflow claim, unknown ID, missing locator, no provenance, quarantine, no exposed identifier, inventory "safe" process; injected evidence text cannot steer the guard | all hold (16 tests). 518 run: 806 checked, 806 accepted. Samples: 52/52 cited steps valid by the repository scorer | PASS |
| M7-4 | `pytest code/synthesis -k m7_4` | NOT_APPLICABLE `[]`; COMPLETE verification-only and cited; rejected citation blocks COMPLETE; no resources ≠ COMPLETE; UNKNOWN never compliance; undecided/contested → no step; INCOMPLETE citation placement; RETAIN never deleted; compliant primary cannot hide violating failover; rejected finding → future check; process cases | all hold (11 tests); full-run property test over 518 | PASS |
| M7-5 | `python3 code/evaluation/m7_metrics.py` | Holdout case acc ≥ 0.90, sequence acc ≥ 0.75, dev step F1 ≥ 0.80 (M5-5) | holdout case acc 0.90 (9/10) PASS; sequence acc dev 0.091, holdout 0.0 **FAIL**; dev step F1 0.792 **FAIL** | **FAIL** |
| Risk overlay | `pytest code/synthesis -k risk or overlay` | Owned index hit is risk; miss, foreign, non-owner and post-cutoff readings are not; a later safe word cancels; NOT_FOUND never proves safety; RETAIN and security retention never change | all hold (6 tests) | PASS |
| End to end | `pytest code/synthesis -k "full_run or cli or serialize"` | 518 rows, sorted, valid JSON arrays, exact 7 fields, consecutive step numbers, allowed operation/state pairs, citation placement; no DELETE on retained categories or backups; M4 UNKNOWN still 308; two CLI runs byte-identical; root `output.csv` refused | all hold | PASS |
| Determinism | `main.py --output A`; `main.py --output B`; `sha256sum` | identical | both `aeb5c135…6fd80e80` (518 rows) | PASS |
| Full suite | `python3 -m pytest -q -p no:cacheprovider code` | M0–M7 pass | see §4.1 | see §4.1 |

### 4.1 Full regression suite
`python3 -m pytest -q -p no:cacheprovider code` → **424 passed** (378 from M0–M6 + 46 M7), 0 failed.
The first run found one leak: the M7 metrics docstring named sample case IDs, which
`test_no_official_answer_ids_in_python_sources` (M0) rejects. The docstring was reworded, and the
suite was re-run clean.

### 4.2 Metrics (repository scorer; dev tuned, holdout report-only and NOT blind)
The holdout (case_23–case_32) answers were seen in earlier milestones. Its numbers are a
consistency check, not a generalization estimate, and nothing was tuned on its labels.

| Split | Run | Status | Step P | Step R | Step F1 | Field acc | Sequence acc | Exact case | Citations valid |
|---|---|---|---|---|---|---|---|---|---|
| dev (22) | M6 provisional | 19/22 | 0.981 | 0.430 | 0.598 | 0.940 | 0.045 | 1/22 | 18/18 |
| dev (22) | **M7** | **19/22** | **0.988** | **0.661** | **0.792** | **0.952** | **0.091** | 2/22 | 26/26 |
| holdout (10) | M6 provisional | 9/10 | 1.000 | 0.736 | 0.848 | 0.930 | 0.0 | 0/10 | 26/26 |
| holdout (10) | **M7** | **9/10** | **1.000** | **0.736** | **0.848** | **0.930** | **0.0** | 0/10 | 26/26 |
| all (32) | M7 | 28/32 | 0.992 | 0.689 | 0.814 | 0.943 | 0.063 | 2/32 | 52/52 |

The "M6 provisional" rows are `evaluation/m6_metrics.combined_row` on the same data, including the
M4 system-less record fix. M6's own report gave dev F1 0.548 before that fix. So the dev step F1
progression is 0.548 (M6) → 0.598 (+ M4 system fix) → **0.792** (M7). Holdout stays 0.848 because
no holdout-only reading was added.

Per-field accuracy on matched steps (all 32): phase, operation, state, `system_id`, `resource_id`
1.0; `evidence_id` 0.992 (one holdout finding cites a different but valid file than the answer, as
in M6); `step_no` 0.609 (positions shift with missing steps). Normalized Kendall tau on matched
steps: 1.0.

518-case run: COMPLETE 88, INCOMPLETE 420, NOT_APPLICABLE 10, with 2,264 steps (1,800 under M6
provisional). Status did not change for any case compared with the M6 provisional synthesis.
Unresolved items: 327 in 235 cases. M4 UNKNOWN latest states: still **308**, and none promoted. The
risk overlay changes 142 copies, and the M4 state of each stays UNKNOWN.

### 4.3 Remaining misses (every missed sample step has a cause)
`m7_metrics.py` lists each step with its cause. Counts:

| Category | dev | holdout | Cause |
|---|---|---|---|
| Unretrieved or unattributed record | 20 | 17 | Mostly the subject's `account_*` profile and `audit_record_*`. The resource ID never appears in any evidence that names the subject: only an activity row (a claim with no identifier), or nothing at all (`account_001/002/004`). Deriving `account_N` from `user_N` would be naming inference. Others are only in screenshots (M8) or join the subject only by line adjacency (`support_002`). |
| M5 condition UNKNOWN | 15 | 2 | 9 dev + 2 holdout steps are rule_12 security audit records with no supplied retention period. They stay UNRESOLVED by owner decision. The other 6 dev steps are two rule_05 support messages (`support_864`, `support_5569`) whose "shared context" condition is not evidenced. |
| Missing policy mapping | 6 | 0 | `support_9553` (a message PII scan only) and `support_001` (a PDF attachment) have ambiguous categories. |

Status misses:
- **case_01, case_02, case_04 (dev):** the subject's account resource is never named in readable
  evidence. "No resources" is not COMPLETE.
- **case_31 (holdout):** a security audit record has no supplied retention period, so it stays
  UNRESOLVED.

The one extra step is `case_17` `VERIFY_RECORD_ABSENT account_6523`, unchanged since M5.

## 5. Known limitations
- M5-5 (dev F1 ≥ 0.80) is still **unmet** at 0.792. The remaining gap is identity and record
  coverage plus the owner's security-retention decision, not synthesis. No target was lowered.
- Sequence accuracy is far below 0.75. Ordering itself is exact (M7-1 32/32, Kendall tau 1.0), but a
  case's sequence matches only when its step set is complete, so this needs record recall.
- Risk readings use asymmetric proof. A wrong FOUND listing or a stale index hit produces a false
  finding (the safe direction). It never produces a false COMPLETE.
- Rows marked INCOMPLETE without a finding (80 of 518) fail the strict M0 plan-shape rule. Whether
  the hidden grader expects some other shape for "uncertain" cases is unknown.
- Screenshots (11 PNGs) are still `needs_multimodal` (M8). Some missing account, analytics and audit
  links may be visible only there.

## 6. Recommendation: FAIL (milestone gates), with M7-1 to M7-4 PASS
Justification: M7-1, M7-2, M7-3 and M7-4 pass with adversarial coverage, deterministic offline
output and 100% citation validity. M7-5 fails on sequence accuracy (dev 0.091, holdout 0.0 against
0.75) and on the carried-over M5-5 step F1 target (dev 0.792 against 0.80). Holdout case accuracy
meets 0.90 exactly. Per the checkpoint rules, a milestone with an unmet target is not marked PASS.
The synthesizer is complete; the remaining gap is record coverage, which needs M8 screenshots,
identity links and owner-level policy decisions.

---

# M7 Rev 2 (independent review corrections, 2026-10-24)

The sections above are the reviewed M7 report and are kept unchanged. This section records the Rev 2
corrections. The holdout (sample case_23 to case_32) is report-only and **not blind**: the sample
answers were viewed during earlier milestones. Nothing in Rev 2 was tuned on it.

## R1. Cross-copy risk contamination (fixed)
- Each `RecordReading` now carries `scope = state.engine.physical_scope(observation)`. That is the
  SQL table for snapshots and the observation topology (default `service`) otherwise, which is the
  same key M4 and M5 use for copies.
- `risk.overlay` groups readings with `by_scope`. A copy can change only from the latest reading of
  **its own** scope. A safe word on one replica can no longer cancel risk on another, and a risky
  primary can no longer promote a failover or reporting copy. The cross-scope `_later_safe_fact`
  helper was removed.
- A risk reading whose scope has no M4 copy is recorded as an unapplied note (`to: null`, "no copy
  state invented"). It never creates a copy or a state.
- M5's worst-copy rollup is unchanged, so two violating copies still give one finding per resource.
- The citation guard compares `physical_scope(cited observation)` with the copy the step relies on,
  before the system check. A citation from another copy is rejected.
- Fixtures added in `code/synthesis/tests/test_synthesis.py`:
  - two copies: a risky primary does not promote the failover;
  - two copies: a later primary miss does not hide an earlier failover hit;
  - three copies (primary, failover, reporting) with conflicting timestamps and states;
  - rollup gives one finding for two violating copies;
  - a logical reading never invents a copy;
  - the guard rejects a citation from another copy.
- On the 518 cases all 142 promotions were already same-scope (`service`: telemetry 93, inventory
  49), so the bug was latent. The 518 output is **byte-identical** to the reviewed run
  (sha256 `aeb5c135…6fd80e80`). There are 0 unapplied readings, and 806/806 citations are accepted
  with the new scope check.

## R2. `*_lookup_completed` rule (removed)
No participant-facing schema documents `*_lookup_completed rows=N` as proof that a record is present.
The rule was inferred from dev error analysis, so it was removed rather than hardened. Ablation:

| run | dev step F1 | dev sequence | dev status | holdout F1 (report-only) | 518 output |
|---|---|---|---|---|---|
| with rule (reviewed) | 0.792 | 0.091 | 19/22 | 0.848 | sha256 aeb5c135… |
| without rule (Rev 2) | 0.780 | 0.091 | 19/22 | 0.848 | identical bytes |

The rule changed only one dev record (one analytics resource in one dev case) and nothing on the 518
cases. It was sample-fitted, so it is dropped. Parametrized tests show that a lookup or query event
is no longer presence evidence for any of these: HTTP 200 with rows=1, a failed HTTP status, a
malformed row count, a started (incomplete) operation, or a conflicting worker status.

## R3. Future-only verification (documented)
- Every future-only check now carries a `future_only` record in the case diagnostics. The record
  lists:
  - the identity sources (`evidence:locator` plus attribution);
  - the rule ID and the required treatment;
  - the condition outcomes and the per-copy states;
  - `current_state_known: false`;
  - why the finding and remediation are omitted;
  - its strict-contract status.
- On the 518 cases there are **41** future-only checks, all `VERIFY_RECORD_ABSENT` for decided DELETE
  records whose M4 state is UNKNOWN. In each, no admissible, subject-owned reading proves the record
  present, so a REPORT_REMAINING_RECORD would be invented. M7 never emits one.
- 30 of the 41 sit in cases that also have an evidenced finding, so those rows meet the strict shape.
  The other 11 are in R4's rows.

## R4. The 80 strict-validator rows
- The strict validator is unchanged and stays the default. The permissive flag was renamed
  `nonstandard_allow_unproven_incomplete`; it is documented as DIAGNOSTIC and NONSTANDARD and is never
  used to claim submission validity. Both results are reported separately (`m7_metrics.py`,
  `reports.py`).

| data | strict M0 | diagnostic NONSTANDARD |
|---|---|---|
| 518 evaluation requests | **FAIL**: 120 errors in 80 rows | PASS, 0 errors |
| 32 public samples | **FAIL**: 12 errors in 7 rows | PASS, 0 errors |

- Per-case investigation: `code/evaluation/checkpoints/M7_INCOMPLETE_WITHOUT_FINDINGS.md`, generated
  by `python3 code/synthesis/reports.py`.
  - Shapes: 40 future-only, 30 with undecided treatments only, 10 with no linked resources.
  - Unresolved causes: unknown conditional treatment 77, unknown state 11, process state unknown 4,
    missing policy mapping 3.
  - Citation rejections: 0. Unapplied risk readings: 0.
- **A strict, source-grounded plan is not possible for any of the 80 rows.** A strict plan needs a
  FINDING, and a FINDING needs an admissible citation that proves presence, exposure or an active
  process at `audit_at`. None exists for these rows. Resource IDs are never inferred from numbering.
- This remains an **unresolved conflict** between the strict plan shape and the evidence. It is left
  visible, not hidden. The open owner decisions are the security-retention condition (77 of the
  causes) and how M10 should serialize "uncertain" cases.

## R5. Preserved behaviour
- M0–M6 tests pass.
- Canonical ordering is exact (M7-1 32/32, Kendall tau 1.0).
- 806/806 citations are accepted.
- Retained records and backups are never deleted (full-run test).
- Security-retention UNKNOWN stays UNRESOLVED.
- Attribution safeguards and quarantines are unchanged.
- No organizer data and no hardcoded answers (the M0 leak grep passes).
- `dataset/` and root `output.csv` are untouched. log.txt is append-only.

## R6. Verification
- `python3 -m pytest -q -p no:cacheprovider code`: **437 passed** (424 reviewed + 13 Rev 2).
- Two 518 runs: byte-identical, sha256 `aeb5c13565bfeda694f8aa15bd80326b9a32f1cb791745b44da84c9acfd80e80`.

| metric | reviewed M7 | Rev 2 | note |
|---|---|---|---|
| dev step precision / recall / F1 | — / — / 0.792 | 0.987 / 0.645 / **0.780** | lookup rule removed (R2) |
| dev case (status) accuracy | 19/22 | 19/22 (0.864) | |
| dev sequence accuracy | 0.091 | 0.091 | |
| holdout F1 / status / sequence (report-only, not blind) | 0.848 / 9/10 / 0.000 | 0.848 / 9/10 / 0.000 | |
| citations accepted / rejected (518) | 806 / 0 | 806 / 0 | the scope check is now included |
| strict validator errors (518) | 120 in 80 rows | 120 in 80 rows | unresolved conflict (R4) |
| INCOMPLETE rows without findings (518) | 80 | 80 | |
| future-only checks (518) | not counted | 41 | |
| risk promotions (518) | 142 | 142 (service/telemetry 93, service/inventory 49; 0 unapplied) | |
| M4 UNKNOWN latest | 308 | 308 | |

The only regression is dev F1 falling from 0.792 to 0.780 (one dev record). It comes entirely from
removing the undocumented lookup rule, as the review asked.

## R7. Gates
| gate | result |
|---|---|
| M7-1 serialization and ordering | PASS |
| M7-2 dependency ordering | PASS |
| M7-3 citation guard (now with scope) | PASS |
| M7-4 status and plan shape | PASS |
| M7-5 targets (sequence ≥ 0.75, F1 ≥ 0.80) | **FAIL** |
| M5-5 carried over (dev F1 ≥ 0.80) | **FAIL** (0.780) |
| strict M0 plan shape on 518 | **FAIL**: unresolved conflict, awaiting owner decision |
| Rev 2 fixes R1–R4 | PASS |
| independent review | PENDING |

Recommendation: **FAIL** at the milestone level. The Rev 2 corrections are complete. M7 is not
merged, and M8–M10 are not started.

## R8. Owner decision on M7 Rev 2 (Harsh, 2026-10-24)
- **Approved for merge** as a safety-reviewed integration baseline at `c589953`. Merge approval is not
  submission approval: the current CSV is **not** declared submission-ready.
- Gates carried forward: M7-5 **FAIL**, M5-5 **FAIL** (dev F1 0.780), strict M0 validation **FAIL**
  (120 errors in 80 rows), final submission readiness **FAIL**.
- The 80 INCOMPLETE rows keep their honest classification. No finding is manufactured to pass the
  validator.
  - A proven violation emits a finding, a remediation and a verification.
  - A known treatment with an UNKNOWN current state stays INCOMPLETE. A future verification without a
    finding is accepted as a provisional representation.
  - No attributable resources: INCOMPLETE with no invented steps.
  - The strict validator failure is preserved and disclosed. It is an internal validator, not
    confirmed hidden-grader behaviour.
- Security retention (rule_12, "within the supplied retention period"):
  - A record is retained under this rule only if the supplied evidence shows the period covers
    `audit_at`.
  - A missing period stays UNKNOWN. No assumed period, no indefinite retention, no automatic deletion.
  - The 77 unknown conditional treatments are items, not distinct cases. They are to be reassessed
    after multimodal (M8) integration, removing only the uncertainty that real evidence resolves.
