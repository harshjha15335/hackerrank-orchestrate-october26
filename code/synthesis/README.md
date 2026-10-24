# M7 step synthesis

`python3 code/synthesis/main.py --output /tmp/m7/predictions.csv` runs M1–M7
on all 518 requests and writes a complete prediction file to that temporary
path. `--sample` uses the 32 public sample requests, `--summary` prints
aggregate counts (status, operations, citation guard, unresolved items,
dependency reorders), and `--case <case_id> --explain` prints one case's row,
diagnostics and every citation check. The CLI refuses root `output.csv` and
anything under `dataset/` (root output is M10's job). It runs offline: M3
intent uses its rules mode and no model is called.

`python3 code/evaluation/m7_metrics.py` is the evaluation-only scorer run (it
alone reads the sample answers): M7-1 serialization fixture, dev/holdout
metrics with the repository scorer, citation validity, and a root cause for
every missed step.

## Pipeline

1. **Inputs.** M2 resolution, M3 intent, M4 latest physical-copy states, M5
   copy decisions, M6 process assessments and dependency edges, all built by
   the existing modules (`synthesis.main.Pipeline`).
2. **Referenced sources** (`risk.referenced_sources`). A record that names
   only the subject and carries `source_resource_id` names the record it was
   derived from. That upstream record is added as an M5 copy with UNKNOWN
   state, and a `record_level` dependency edge is kept. Its system must come
   from admissible activity rows that all name the same system.
3. **Risk overlay** (`risk.overlay`). This is M6's asymmetric-proof rule
   applied to records. Owning-service telemetry, inventory listings and
   owning-system artifacts can show that a record is still present or still
   exposed. Only an UNRESOLVED copy whose M4 state is UNKNOWN can change, and
   only to VIOLATION:
   - a decided DELETE becomes a violation on PRESENT;
   - a decided REDACT or ANONYMIZE becomes a violation on an exposure
     reading;
   - an UNKNOWN `still_attributable` condition becomes TRUE on an exposure
     reading;
   - an UNKNOWN `contains_email_address` condition becomes TRUE on a matched
     email.

   RETAIN records and the security-retention condition are never decided
   here. A later NOT_FOUND, miss or `available=false` reading cancels the
   risk, but it never proves compliance. M4 states and M5 decisions are not
   modified.
4. **Plan and status** (`synthesizer.plan`, `synthesize`). See the module
   docstring. NOT_APPLICABLE gives `[]`. COMPLETE needs at least one resource
   or process, every copy COMPLIANT, every process proven safe, nothing
   unresolved, and every verification citation accepted. Everything else is
   INCOMPLETE. An UNRESOLVED record whose treatment is decided gets only its
   future verification. A record whose treatment is undecided, or whose
   attribution is contested, gets no step. It is listed in `unresolved`.
5. **Citation guard** (`citations.CitationGuard`). It re-reads every cited
   observation and checks the ID, the time, the M4/M5 temporal gate and
   quarantine, the resource and system, that the source is not a claim,
   subject-only attribution, and that the state supports the operation. A
   rejected finding leaves the record unproven (future check only). A
   rejected COMPLETE verification makes the case INCOMPLETE.
6. **Order** (`ordering`). Canonical order is phase, then operation-table
   order, then `system_id`, then `resource_id`. The dependency hook reorders
   only same-operation remediation pairs joined by a `record_level`
   downstream→source edge, and reports cross-operation conflicts and cycles.
   Steps are then renumbered from 1.

## Output contract notes

An INCOMPLETE case can have nothing provable to report. That happens when the
subject has no linked resource, or every gap is an undecided treatment. Such
a case carries either no steps or only future verification steps. It never
carries an invented finding. `validate_rows(..., allow_unproven_incomplete=True)`
accepts that shape. Without the flag (the M0 default), such a case is an error.
