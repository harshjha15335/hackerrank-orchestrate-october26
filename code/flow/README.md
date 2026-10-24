# M6 active data flows and restore paths

Run `python3 code/flow/main.py --case case_15 --sample` to inspect one sample
case, `python3 code/flow/main.py --sample` for all 32 samples, or
`python3 code/flow/main.py --summary` for aggregate counts over the 518
evaluation cases. `--with-policy` keeps the embedded M5 policy output.
Output is deterministic JSON on stdout; nothing writes `output.csv`.
`python3 code/flow/reports.py` regenerates
`code/evaluation/checkpoints/M6_FLOW_DIAGNOSTICS.md`, and
`python3 code/evaluation/m6_metrics.py` prints the evaluation-only
development/holdout metrics (it alone reads sample gold).

## What it assesses

A process resource is an `integration_service` `data_flow_*` connector or a
`backup_service` `backup_*` restore path. Only that explicit system + resource
prefix identifies one; a flow-like log line without a resource ID, or a
`data_flow_*` ID reported by another service, is not a process.

`evidence.py` turns each M1 observation of a process resource into a reading:
state (ACTIVE / DISABLED / RESTORE_ENABLED / RESTORE_BLOCKED / UNKNOWN), the
time it was seen to hold, and an evidence class:

| Class | Source | Can show risk | Can prove safe state |
|---|---|---|---|
| snapshot | SQL `connector_subscriptions.enabled`, `backup_restore_entries.restore_allowed` (M4) | yes | yes |
| readback | completed `connector_config_read_completed` / `restore_policy_read_completed` (M4) | yes | yes |
| field_values | JSON connector / restore entries with explicit `enabled` / `restore_allowed` (M4) | yes | yes |
| telemetry | owning-service, resource-scoped `connector_heartbeat`, `connector_config_loaded`, `restore_candidate_evaluated`, `restore_authorization_completed` | yes | yes |
| inventory | another service's listing (handover lines, `record_type` + `result` records, `record_lookup` logs) | yes | no |
| claim | `CHECK_DATA_FLOW`, `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`, `CHECK_RESTORE_ACCESS` activity rows | no | no |

`archive_present`, a FOUND backup or a worker SUCCESS is never a restore or
flow state.

`engine.py` assesses each process per case:

1. **Ownership.** A reading counts only when its own record names the subject
   and nobody else in the cutoff-time identity view (direct), or it carries no
   identifier and shares an explicit trace ID, in the same file, with lines
   that name only the subject (trace). Same resource ID, same file, same event
   stream or similar names are not ownership. A same-ID reading naming another
   person makes the assessment CONFLICTING.
2. **Time.** The M4/M5 gate: nothing captured, emitted or recorded after
   `audit_at` (inclusive boundary) or after its own capture, and nothing M1
   quarantined.
3. **Latest state.** The latest owned, admissible, stateful reading decides
   (ties broken by evidence class reliability, then ID). Disagreeing readings
   at the same observation time are CONFLICTING. A safe state from an
   inventory listing is UNKNOWN. Later unverified workflow claims are kept in
   `later_unverified_claims` and never change the state.
4. **Obligations.** ACTIVE → `REPORT_ACTIVE_DATA_FLOW`/`DISABLE_DATA_FLOW`/
   `VERIFY_DATA_FLOW_DISABLED`; DISABLED → `VERIFY_DATA_FLOW_DISABLED`;
   RESTORE_ENABLED → `REPORT_RESTORE_RISK`/`BLOCK_RESTORE`/
   `VERIFY_RESTORE_BLOCKED`; RESTORE_BLOCKED → `VERIFY_RESTORE_BLOCKED`.
   Each obligation is marked `observed` (cites the deciding reading) or
   `proposed` (future work, empty evidence). UNKNOWN and CONFLICTING carry no
   obligations and never imply safety.

Backups stay under M5's `BACKUP_ARCHIVE` rule (RETAIN); each restore
assessment carries that rule and `delete_forbidden`, and M6 never proposes
`DELETE_RECORD`.

`dependencies.py` records evidenced edges for M7: `recreated_by_sync` /
`recreated_by_restore` (an activity row naming the subject's process and the
downstream record it repopulated), `derived_from_source_system` (a derivation
event naming only the downstream record; the upstream stays unnamed),
`flow_destination` (a connector's configured destination) and
`physical_copies` (one resource in several topologies). `precedence`
recommends stopping every supported active flow or enabled restore before any
record remediation in the case; system-level edges are marked as such. M7
owns final step order, citations and case status.
