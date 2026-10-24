# M4 audit-time state reconstruction

Run `python3 code/state/main.py --case case_05 --sample` to inspect one
participant sample case, `python3 code/state/main.py --sample` for all 32
samples, or `python3 code/state/main.py` for all 518 evaluation cases. The
commands emit deterministic JSON to stdout and use an optional parser cache
under `/tmp/m4-ingest-cache`. They do not write `output.csv` or read sample
answers. The separate evaluation-only command
`python3 code/evaluation/m4_baseline.py` reads gold to measure a deliberately
provisional DELETE-all status baseline on the first 22 samples.

Each assertion retains source ID and locator, capture/event/record time,
physical scope, identity strength, observation class, state and explanation.
Latest facts are selected per system, resource and physical scope. Capture
time, event time, evidence reliability and source locator provide stable
ordering. Equal-time opposing direct facts become UNKNOWN; older opposing
facts remain in the assertion history and conflict list. A later verified
readback can supersede an earlier one within the same scope. Different SQL
tables are distinct copies, so primary deletion does not erase a replica.

SQL rows and validated field-level/readback results are observed states.
Connector and restore flags use one strict boolean parser across SQL, JSON
and completed log readbacks. Missing or unrecognized flags yield UNKNOWN;
log flags require a matching completed event, service, resource and time.
Activity SUCCESS, bare FOUND strings and other operational messages remain
UNKNOWN unless corroborated. HTTP 200/404 is accepted only on a completed,
resource-scoped readback. A source record time after the manifest capture or
the case cutoff is quarantined; raw evidence remains unchanged. Negative SQL
states require a direct or independently verified customer reference and an
explicitly complete point-in-time primary/failover account table. Other
SnapshotIndex scopes remain candidates, not confirmed absence.

`UNKNOWN` is intentional where the source is a claim, attribution is mixed,
or the observed scope is insufficient. `attribution` distinguishes direct,
context and trace-correlated links. This stage does not apply retention policy,
plan remediation, infer ownership from sample answers, or decide final status.

M5 review addendum: a completed, resource- and service-matched readback that
returns record fields without row/HTTP keys, and a JSON record with non-null
fields of its own (not a `result` claim), are field-level observations. They
yield PRESENT, REDACTED (account/support rows without direct identifiers) or
ANONYMIZED (analytics with retained content), and otherwise stay UNKNOWN.
