# M4 — audit-time state reconstruction — corrected for independent review

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

Independent review found that completed connector/restore log readbacks were
discarded when they lacked HTTP or row-count fields, and invalid JSON flags
could be interpreted as safe false values. `parse_source_bool()` now accepts
only JSON booleans, SQLite integer 0/1 and explicit `true`/`false` or `1`/`0`
text. Missing, null, malformed, floating-point and ambiguous values yield
UNKNOWN across SQL, JSON and log sources. A completed log event must name the
expected service and resource type, have a matching resource ID and event
time, and have no contradictory row-count or status metadata. Its flag state
takes precedence over a generic PRESENT readback. Delivery status and worker
results do not establish flow or restore state.

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
| M4-5 | Provisional first-22 development-sample status accuracy with a DELETE-all M5 stub: **14/22 (63.6%)** after the readback correction; previously 12/22. No M5 policy, step planning or final accuracy claim. |

The 518 evaluation cases have **1,440** latest physical-resource assertions:
**1,075** source-supported states and **365 UNKNOWN**. Latest states are
PRESENT 750, ABSENT 38, REDACTED 81, ANONYMIZED 0, ACTIVE 107, DISABLED 36,
RESTORE_ENABLED 27 and RESTORE_BLOCKED 36. The case-specific latest views
contain **0** opposing-fact conflicts, **0** replica drift, and **0** cutoff
violations; synthetic conflicting-fact tests prove the unresolved path. The
32 samples have 80 latest assertions, 46 supported and 34 UNKNOWN, with one
real SQL drift. Per-case histories preserve 1,094 UNKNOWN claim assertions
in the full run rather than converting claims into compliance evidence.

Before/after full-run counts: supported **1,028 → 1,075**; UNKNOWN
**412 → 365**; ACTIVE **86 → 107**; DISABLED **25 → 36**;
RESTORE_ENABLED **23 → 27**; RESTORE_BLOCKED **25 → 36**. The remaining state
categories and the 1,440-resource denominator are unchanged. Provisional
development status accuracy changed **12/22 → 14/22**. Replica drift,
opposing-fact conflicts and cutoff violations remained **0/0/0** on the 518
cases; the real sample SQL drift remained **1**. These changes arise from
validated source readbacks, not answer-specific rules.

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
reported **217 passed** after correction, zero failures/skips. Two full CLI runs
matched byte-for-byte, SHA-256
`5fa436635072568b10229ef49a68eab8c875e649e5d6109efdec12f067863156`.
The sample inspection SHA-256 was
`4dc1ef85cc59a2fdedb4bf7d2da9bc02f8d063e1bf7b4dd5ebe694b52538bee3`.
The baseline command is `python3 code/evaluation/m4_baseline.py`.
The added regressions cover completed true/false connector and restore
readbacks, four participant-observed event/flag combinations, invalid values
on every source type, unfinished and unscoped events, contradictory metadata,
provenance, temporal transitions and timezone-aware cutoff boundaries.

Trenton's pinned May source
`benchmarks/trenton/code/agent/pipeline.py:107-118` escalates a claimed
"replied" outcome if corpus retrieval never occurred. October extends that
principle to timestamped, per-copy source facts: workflow success alone is
not deletion proof, and a read of one store cannot prove every other store
empty. May's support-ticket status metrics are not reused.

**PASS recommendation for renewed M4 independent review, with 365 explicitly unresolved latest
states and four unattributed sample references.** M5 must apply policy and
later milestones must assess omitted resources, source authority beyond the
explicit SQL comparison tables, and attribution of currently unlinked records.
The 14/22 provisional status baseline is not final deletion-decision accuracy.

## Addendum (2026-10-24, M5 review correction)
Two narrowly scoped M4 state rules (completed readbacks that return record fields; JSON records with
their own fields) and an M1 pipe-log parser fix were added on `feature/m5-policy-engine`. The figures
above describe the reviewed M4 commit; current counts are in `M5_report.md` §R2–R4 (UNKNOWN 365 → 245,
no previously supported state changed, provisional DELETE-all dev status 14/22 → 13/22).
