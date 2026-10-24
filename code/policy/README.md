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
attribution. Backups keep the RETAIN
verdict and carry a separate restore obligation.

This stage does not plan data flows (M6), order or cite final steps, or decide
case status (M7). `code/evaluation/m5_metrics.py` builds a provisional,
evaluation-only steps array to measure the development split.
