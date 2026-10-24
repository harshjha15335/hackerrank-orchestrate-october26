# M4 — audit-time state reconstruction — PASS for independent review

Date: 2026-10-24. Branch: `feature/m4-state-reconstruction` from verified
merged M3 `main` at `6c3eb90d42c8b2338434c97b491a6da579e4620b`.

## Implementation

`code/state/engine.py` defines typed state assertions with case, user,
system/resource/category, state, evidence ID and locator, capture/event/record
times, physical SQL table/topology, attribution, reliability class, conflict
references and explanation. `code/state/main.py` inspects one case or all
cases. `code/state/tests/test_state.py` tests synthetic timelines, cutoff,
source reliability, conflicts, SQL scope and a participant-derived replica
fixture. `code/evaluation/m4_baseline.py` alone reads sample gold for the
provisional metric. The narrow M3 mixed-negation correction adds two tests.
`code/main.py`, the official dataset and root `output.csv` are unchanged.

Observed SQL rows, field-level JSON, and completed scoped HTTP/row-count
readbacks can support states. Workflow/activity successes and bare `FOUND`
strings remain claims with `UNKNOWN` state. HTTP 404 with zero rows supports
absence only for the queried resource/scope. Retained null-identifier account
and support rows are REDACTED, not absent. Analytics rows with actual fields
but no direct identifiers are ANONYMIZED when safely linked. Connector
`enabled` and backup `restore_allowed` fields yield separate ACTIVE/DISABLED
and RESTORE_ENABLED/RESTORE_BLOCKED states. Neither is a final policy verdict.

The latest supported observation wins within one physical scope by capture
time, then event time, reliability and stable source locator. Equal-time
opposing facts become UNKNOWN and both remain in history. Primary, read,
reporting, regional and failover SQL tables stay separate. Later claims do
not erase earlier facts. An independently attributed resource and the
participant SQL file's explicit complete point-in-time primary/failover
tables are required before `SnapshotIndex.absence_candidate()` can become an
ABSENT assertion. Other SQL tables do not supply negative proof.

## Checkpoint results

| Gate | Result |
|---|---|
| M4-1 | 518/518 cases reconstructed; **0** post-cutoff capture violations using aware datetimes. Two later-than-capture JSON record times were quarantined, not rewritten. |
| M4-2 | Deterministic latest-state and tie tests pass; verified 404 → 200 yields PRESENT and 200 → verified 404 yields ABSENT within one scope. Opposing equal-time facts yield UNKNOWN. Full-run JSON repeated byte-identically. |
| M4-3 | Synthetic worker/activity `reported_result=SUCCESS` and generic `result=FOUND` both remain UNKNOWN without a source readback. |
| M4-4 | Participant SQL topology fixture: one independently identified account is ABSENT in the complete primary table but PRESENT in the failover table. Sample inspection reports one physical-copy drift; the 518 evaluation cases report zero drift at their cutoffs. |
| M4-5 | Provisional first-22 development-sample status accuracy with a DELETE-all M5 stub: **12/22 (54.5%)**. No M5 policy, step planning or final accuracy claim. |

The 518 evaluation cases have **1,440** latest physical-resource assertions:
**1,028** source-supported states and **412 UNKNOWN**. Latest states are
PRESENT 750, ABSENT 38, REDACTED 81, ANONYMIZED 0, ACTIVE 86, DISABLED 25,
RESTORE_ENABLED 23 and RESTORE_BLOCKED 25. The case-specific latest views
contain **0** opposing-fact conflicts, **0** replica drift, and **0** cutoff
violations; synthetic conflicting-fact tests prove the unresolved path. The
32 samples have 80 latest assertions, 44 supported and 36 UNKNOWN, with one
real SQL drift. Per-case histories preserve 1,141 UNKNOWN claim assertions
in the full run rather than converting claims into compliance evidence.

The four M2 unattributed references remain unresolved:
`analytics_9406` (null-identifier log lookup), `analytics_901`
(null-identifier JSON report), `account_6440` (unattributed profile lookup)
and `analytics_5335` (null-identifier service export). Activity resource IDs
and array positions do not establish customer ownership. None appears as a
linked assertion in the sample inspection. These diagnostic names occur only
in this evaluation report, not production decisions. The two unchanged M1
timestamp discrepancies are `evidence_13` at `$.records[38]` and
`evidence_36` at `$.records[45]`; their source times are preserved and their
state assertions quarantined when reached.

## Verification and comparison

`/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider
code/evaluation/tests code/ingest/tests code/identity/tests code/intent/tests code/state/tests`
reported **170 passed in 22.14s**, zero failures/skips. Two full CLI runs
matched byte-for-byte, SHA-256
`830f531719f3695dce2b37ff24aed93c3fd141c47c35e51d9ae7218c7f4cab2b`.
The sample inspection SHA-256 was
`6197ca9701654c1b71f38c45bed35316460de1601dfcf0d5e185e953a38e2aad`.
The baseline command is `python3 code/evaluation/m4_baseline.py`.

Trenton's pinned May source
`benchmarks/trenton/code/agent/pipeline.py:107-118` escalates a claimed
"replied" outcome if corpus retrieval never occurred. October extends that
principle to timestamped, per-copy source facts: workflow success alone is
not deletion proof, and a read of one store cannot prove every other store
empty. May's support-ticket status metrics are not reused.

**PASS for M4 independent review, with 412 explicitly unresolved latest
states and four unattributed sample references.** M5 must apply policy and
later milestones must assess omitted resources, source authority beyond the
explicit SQL comparison tables, and attribution of currently unlinked records.
The 12/22 provisional status baseline is not final deletion-decision accuracy.
