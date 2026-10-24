# M0 contract harness

Runtime: Python >=3.11, standard library only. Development tests use
`python3 -m pip install -r code/evaluation/requirements-test.txt`.
Run from the repository root:

```sh
python3 code/evaluation/main.py validate dataset/sample_output.csv --mode sample
python3 code/evaluation/main.py validate /path/to/submission.csv --mode full
python3 code/evaluation/main.py score /path/to/sample_predictions.csv
python3 -m pytest -q -p no:cacheprovider code/evaluation/tests
python3 code/main.py --output /tmp/new-m0-stub.csv
```

Validation and scoring emit deterministic JSON to stdout. Exit 0 means valid
output (and exact sample agreement for `score`); exit 1 means invalid output,
scoring input error, or a sample mismatch. Argument errors use exit 2. `score`
also reports parseable semantically invalid predictions so ordering, citation,
and completeness errors remain measurable; validation errors remain visible.
Unparseable CSV/JSON or incorrectly typed step shapes cannot be scored.
No command writes predictions except the explicitly labelled format-only stub.
The stub requires a new destination, rejects root `output.csv` and all paths
under `dataset/`, and always emits `NOT_APPLICABLE,[]`. It is not an audit agent
and its format validity says nothing about prediction correctness.

The validator enforces the **seven** fields in the official contract. It loads
case IDs/cutoffs from the chosen request file, never from answers. Evidence IDs
come from the manifest, activity and audit CSVs. Cutoffs are inclusive with
timezone-aware comparisons. Every finding must have a compatible remediation
on the same system/resource; each remediation must have its corresponding
verification. Additional verification for already compliant/retained records
is allowed. Evidence membership/time checks do not prove factual support,
identity linkage, policy compliance, or completeness of undiscovered resources.
Dependency-aware ordering from AGENTS.md cannot be inferred from output alone;
M0 enforces the explicit operation-table sort in the problem statement.

## Metrics and denominators

Gold is loaded only by the evaluation module (`scorer.evaluate_sample`), never
the production entry point. The 32 sample requests define fixed splits: the
first 22 sorted IDs are dev and the remaining 10 holdout. All-sample results
include unexpected predicted cases as penalties; unexpected IDs have no split
assignment and are omitted from dev/holdout. Missing cases never disappear from
denominators. Duplicate case IDs are rejected rather than overwritten.

Let `C` be the union of predicted and gold case IDs for a split, `P_c` and `G_c`
their ordered step arrays, and `K(s)=(phase, operation, system_id, resource_id)`.
Missing sides have zero steps but always fail case-level comparisons.
Let `M = sum_c |multiset(K(P_c)) intersect multiset(K(G_c))|`,
`P=sum_c len(P_c)`, `G=sum_c len(G_c)`, and
`S=sum_c max(len(P_c),len(G_c))`.

| Metric | Numerator / denominator |
|---|---|
| `status_accuracy` | Cases present on both sides with exact status equality / `len(C)` |
| `case_exact_match` | Cases present on both sides with equal status and all ordered step fields / `len(C)` |
| `step_count_accuracy` | Cases present on both sides with equal array lengths / `len(C)` |
| `step_precision`, `step_recall` | `M/P`, `M/G` (micro, duplicate occurrences retained) |
| `step_f1` | `2*M/(P+G)` |
| `operation_accuracy` | Same-position exact operation matches / `S` |
| `system_id_accuracy`, `resource_id_accuracy` | Same-position exact field matches / `S`, separately |
| `evidence_id_accuracy` | Same-position exact evidence ID matches (including empty strings) / `S` |
| `field_accuracy` | Equal fields across canonical-key matched steps / `7*M` |
| `matched_field_accuracy[field]` | Equal values for that field among canonical-key matched steps / `M`, for each of seven fields |
| `sequence_accuracy` | Cases present on both sides with identical ordered canonical-key lists / `len(C)` |
| `normalised_kendall_tau` | Concordant matched occurrence pairs / all within-case matched occurrence pairs, micro pooled; equals `(tau+1)/2` |
| `evidence_validity_rate` | Predicted nonempty citations known and at/before that case's cutoff / all predicted nonempty citations |

Matched steps pair FIFO among equal canonical keys, preserving duplicate
occurrences deterministically. `step_no`, `state`, and `evidence_id` can differ
among these pairs; the four key fields necessarily match. Positional metrics
provide separate diagnostics for those key fields and penalize missing/extra
slots. Empty evidence strings are included in evidence *accuracy*, excluded
from evidence *validity*. No citation is treated as proof of content grounding.

Every ratio is reported with numerator, denominator and value. Zero-denominator
ratios are 1 by vacuous convention, except precision/recall and matched field
accuracy are 0 when one step set is nonempty and no comparison is possible.
Kendall agreement with fewer than two matched steps and citation validity with
no citations are 1, with denominator 0 explicitly exposed. Read these alongside
recall/coverage; they do not imply that missing predictions are correct.
`step_f1` is 1 only when both step multisets are empty if its denominator is 0.

Mismatches list missing/unexpected cases, status differences, and every unequal
step position with expected/actual objects (including null for absent steps).
JSON object-key order and whitespace are ignored; arrays and string values
remain exact. There is no fuzzy matching, case folding, distribution quota,
inference judge, or automatic output repair.

## M6 metrics

`python3 code/evaluation/m6_metrics.py` scores flow/restore steps
(`REPORT_ACTIVE_DATA_FLOW`, `DISABLE_DATA_FLOW`, `VERIFY_DATA_FLOW_DISABLED`,
`REPORT_RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED`) per split and
explains each missed or extra expected obligation from the M6 assessment. It
also scores a provisional M5+M6 steps_json (operation-table order, no M7
citation guard) before and after M6. Holdout numbers are report-only.
