# M5 policy engine

Run `python3 code/policy/main.py --case case_05 --sample` to inspect one sample
case, `python3 code/policy/main.py --sample` for all 32 samples, or
`python3 code/policy/main.py --summary` for aggregate counts over the 518
evaluation cases. `--rules PATH` swaps in another `deletion_rules.csv`.
Output is deterministic JSON on stdout; nothing writes `output.csv`.
`python3 code/policy/reports.py` regenerates the UNKNOWN root-cause and
condition-coverage reports under `code/evaluation/checkpoints/`.

The engine consumes M4 latest physical-copy assertions and the M1 observations
behind them. For each copy it:

1. maps the record to a policy category with `category_map.json` (explicit
   source label > collection/table > record fields > readback event >
   system+resource prefix; disagreement at the winning rank is AMBIGUOUS);
2. loads the matching rule from `dataset/deletion_rules.csv` at runtime;
3. evaluates the rule's condition as TRUE/FALSE/UNKNOWN at `audit_at` with a
   predicate bound by the SHA-256 of the condition wording in
   `condition_bindings.json` (edited wording becomes UNKNOWN);
4. derives the effective action (`on_false` says whether a FALSE condition
   means the target already holds, the authorised deletion applies, or no rule
   decides) and checks the observed state and exposed identifier fields.

Results are COMPLIANT, VIOLATION, UNRESOLVED or DEFERRED_M6 (data flows).
UNKNOWN M4 states, unmapped or ambiguous categories and unbound or UNKNOWN
conditions are always UNRESOLVED. Stable internal references
(`subject_reference`) are permitted on tombstones and support messages; direct
identifiers, including those inside free text, are exposure. Physical copies
roll up per resource with the worst copy deciding. A same-ID record that is
not already subject-linked by M2/M4 is used for conditions or categories only
when every identifier it names (email, phone, hash, user reference) belongs to
the subject's cutoff-time identity view; a shared resource ID alone is never
attribution. Already-linked M2/M4 records are re-checked the same way: a record
naming another person is kept in `attribution_conflicts` and makes the copy
UNRESOLVED; an identifier-free record counts only through an explicit trace
join. Evidence captured, recorded or emitted after `audit_at` (or after its own
capture), or quarantined by M1, never decides a condition. Backups keep the RETAIN
verdict and carry a separate restore obligation.

Rule 07/08 (pre-M9 F-02): explicitly null identifier columns are not proof of
irreversible anonymization. `conditions.anonymization_state` separates direct
identifiers exposed, indirect identifiers that co-occur with the subject's
identifiers elsewhere (both TRUE), indirect identifiers present, identifiers
removed or merely not displayed (UNKNOWN), and an evidenced anonymization:
an ANONYMIZE_RECORD operation on the same system and resource that a later
source read with removed identifiers corroborates, with no indirect identifier
and no later copy naming the subject (FALSE). A support_platform
`message_pii_scan` classifies its resource as SUPPORT_MESSAGE
(`category_map.json`); `[REDACTED]` message text is not observed content. A
support document that merely references a support record (for example an
attached file's properties) does not classify that record: the attached file
is a separate resource with no identifier in the evidence.

This stage does not plan data flows (M6), order or cite final steps, or decide
case status (M7). `code/evaluation/m5_metrics.py` builds a provisional,
evaluation-only steps array to measure the development split.
