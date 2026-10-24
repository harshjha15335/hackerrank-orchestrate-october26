# M0 — Contract harness and scorer — PASS

Date: 2026-10-24. Baseline: `8e3c9d52f78f7d9fde5b00e83aa397ef2474711f`.
Implementation and this report are committed together as the local M0 milestone.

## Implementation

- `code/evaluation/contract.py`: strict CSV/JSON reader, seven-field typed step
  schema, case membership, status invariants, operation-table sorting, citation
  existence/time checks, and structurally detectable remediation/verification
  coverage. Unknown values are rejected without coercion.
- `code/evaluation/scorer.py`: exact case-ID alignment, canonical-key multiset
  precision/recall/F1, positional diagnostics, matched field accuracy, sequence
  and normalised Kendall agreement, citation validity, per-case differences,
  fixed 22/10 dev/holdout splits. Only evaluation code loads sample answers.
- `code/evaluation/main.py`: deterministic JSON CLI; nonzero exit on validation
  errors, scoring input errors, or sample disagreement.
- `code/evaluation/tests/{conftest.py,test_m0.py}`: 83 offline tests, including
  synthetic negative cases and integration/subprocess checks. In-process network
  connections are blocked by an automatic fixture; no inference clients exist.
- `code/main.py`: explicitly labelled format-only full-size stub. Requires an
  explicit, new destination; protects root `output.csv`, dataset files and
  existing artifacts. Does not inspect requests' meaning or read gold.
- `code/evaluation/README.md`: reproducible commands, all formulas and
  denominators, empty-set conventions, split and matching policies.
- `code/evaluation/requirements-test.txt`: pytest 8.3.5. Runtime is standard
  library only; `.gitignore` excludes Python caches. No `code/__init__.py`.

The user confirmed the official **seven-field** schema overrides the earlier
six-field typo. Both six- and eight-field negative cases are rejected.
The benchmark's Pydantic suggestion is implemented with explicit standard-library
type/enum checks instead: no coercion, fewer runtime dependencies, equivalent
contract coverage. No M1 work is included.

## May sources inspected and October differences

Restored ignored reference clones at the exact previously audited commits.
This was a focused inspection of evaluation/testing source, not a rerun of the
May benchmarking phase. No May source was copied or changed; all four Git
working directories were checked clean after inspection.

| Reference and commit | Actual source inspected | Behavior and M0 difference |
|---|---|---|
| saai `fadb4f24e36d860a9ce4d5155bb30568df80ea4b` | `benchmarks/saai-winner/code/schema.py`, `code/runner/pipeline.py:153`, `code/runner/eval_sample.py:33` | Typed enums plus coercion to defaults; sample scorer uses positional zip/min length, normalised labels, and nonempty-gold-area denominator. M0 rejects invalid output, aligns exact IDs, penalises missing/extra cases, and measures structured steps and order. Its citation diagnostics are useful inspiration, but M0 checks October participant IDs and audit cutoffs rather than paths read by a support agent. |
| trenton `c5c765749c1f40469fc3a0c79bfa3ba01085df79` | `benchmarks/trenton/code/eval/scorer.py`, `code/eval/retrieval_scorer.py:141` | Distinguishes official CSV gold from provisional JSON agreement; matches normalised issue text, increments classification denominators only on matched rows; recall@k scorer measures article retrieval. M0 uses only official October sample gold, exact case IDs, full case denominators and multiset step recall, without top-k support-article assumptions. |
| leerenjie `94ed9d6e93b566b1b22c30b910da8319448298ff` | `benchmarks/leerenjie/code/main.py:374`, `code/tests/test_verifier.py` and test-directory inventory | Whole-file column/enumeration/cross-field checks include a 5–50% escalation band. Verifier tests inject fake model calls. M0 adopts offline testing and whole-file checks, omits distribution assumptions and model judges, and adds exact step/evidence/coverage checks. Keeping `code/` outside a package permits pytest's normal debugger plugin. |
| amogh `54f1b0c991e0e8091815c4169f22d31cda749d7a` | `benchmarks/amogh/code/evaluate.py:73`, `code/test_classifier.py` | Positional sample evaluator truncates to fewer predictions, allows partial product-area matches and uses a 70% threshold; classifier tests use plain assertions. M0 tests contract mutations and scorer sensitivity, reports exact field/sequence errors, and requires exact self-agreement with no borrowed May accuracy threshold. |

Only path prefixes in the first source of each cell are repeated; subsequent
`code/...` paths in that cell refer to that same benchmark repository.
No claims about May hidden-label accuracy or fresh May suite results are made.

## Executed checks

Runtime: Python 3.12.14; pytest 8.3.5 in `/tmp/m0-venv`.
Pytest was installed from PyPI after the initial sandbox-network attempt failed;
the allowed network retry succeeded. No paid inference API calls were made.
Tests run with the normal debugging plugin enabled.

| ID | Exact command/check | Actual result |
|---|---|---|
| M0-1 | `python3 code/evaluation/main.py validate dataset/sample_output.csv --mode sample` | Exit 0; 32 rows valid; no errors |
| M0-2 | `/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider code/evaluation/tests` | **83 passed in 0.77s**, zero failed/skipped; includes every required mutation |
| M0-3 | `python3 code/evaluation/main.py score dataset/sample_output.csv` | Exit 0; all metrics 1.0 in all/dev/holdout; no mismatches |
| M0-4 | `test_score_drop_step_denominators`, `test_score_swap_steps`, `test_score_evidence_mutation` within the suite | Synthetic three-step case: drop → recall 2/3, precision 1, F1 4/5; swap → sequence 0, F1 1, Kendall agreement 2/3; evidence change → field accuracy 20/21, evidence accuracy 2/3, validity 0 |
| M0-5 | `python3 code/main.py --output /tmp/m0-proof-cfvd9s0g/stub-a.csv` and same command with `stub-b.csv`; `python3 code/evaluation/main.py validate /tmp/m0-proof-cfvd9s0g/stub-a.csv --mode full` and same with `stub-b.csv` | Both exit 0, 518 sorted unique rows; identical SHA-256 below |
| M0-6 | Normal pytest command above; `test_full_stub_determinism_and_protected_paths` | No `code/__init__.py`, no debugger workaround; root output and official sample remain protected |
| Integrity | `git diff --check`; official gold SHA-256 before/after test; Python-source scan for all sample case/resource/evidence IDs; `git -C benchmarks/<alias> status --porcelain` | Clean formatting, unchanged official files, zero hardcoded answer IDs, all four benchmark clones clean |

The 83 tests include 37 parametrised contract mutations, valid statuses,
five remediation-to-verification mappings, CSV quoting/embedded JSON/Unicode,
JSON duplicate fields and nonstandard constants, exact headers, malformed rows,
evidence cutoff boundaries, strict number types, missing/duplicate/extra cases,
sample/full separation, missing files, CLI exit codes, deterministic reporting,
duplicate-step multiset accounting, metric empty conventions, production/gold
separation, and full-stub determinism/protected paths. All negative fixtures are
synthetic. The first run passed 73 tests; ten additional edge checks also passed.
There are no outstanding failed tests.

Self-evaluation (harness identity check, **not predictor accuracy**):

| Split | Cases | Status | Exact case | Step F1 | Matched field | Sequence |
|---|---:|---:|---:|---:|---:|---:|
| Dev | 22 | 22/22 | 22/22 | 242/242 | 847/847 | 22/22 |
| Holdout | 10 | 10/10 | 10/10 | 144/144 | 504/504 | 10/10 |
| All | 32 | 32/32 | 32/32 | 386/386 | 1351/1351 | 32/32 |

All other self-score ratios (step counts, precision, recall, positional
operation/system/resource/evidence fields, per-field matched accuracy, Kendall
agreement and evidence validity) are 1.0. The self-score contains 193 steps.
Two score CLI runs were byte-identical, SHA-256
`7e997b79fb22e740b87f910216bc51301cf7b76d6156c6222009dd40aca1922c`.
Both stub files have SHA-256
`be3058f7bb0ad0a18fffb1aa0d4419ed5a67c5c8cd78ba0c165f193b30904e8c`.
Temporary proof files are local artifacts; the tests reproduce these checks.

## Known limitations

- Structural validity does not establish correct deletion intent, identity,
  policy, current state, evidence content grounding, or exhaustive coverage of
  relevant resources. Those capabilities belong to later milestones. A known
  citation before the cutoff may still be factually irrelevant.
- Verification coverage can be enforced for emitted remediation operations,
  and compatible remediation for emitted findings. M0 cannot identify omitted
  resources or required retained records from an output file alone.
- Operation-table ordering is enforced; dependencies between resources cannot
  be inferred from the output alone. Evidence-dependent overrides remain M7.
- Matched-field metrics are conditional on canonical matches; they must be read
  with step precision/recall and positional metrics. All denominator/empty-set
  conventions are documented in the evaluation README.
- Self-scoring the gold file only tests evaluator identity. The full-size stub
  is intentionally semantically wrong and is not evaluated as an audit agent.
- Exact runtime model ID is not exposed to this session. New append-only logs
  explicitly record that limitation rather than inventing an ID; prior agents'
  log entries are preserved. This is an exception to AGENTS.md's exact-ID
  logging requirement, not an M0 correctness claim.

## Recommendation: PASS

All M0-1 through M0-6 acceptance checks pass. Official samples and root
`output.csv` were not modified; production code cannot load gold. No benchmark
repository modifications or paid inference occurred. M0 is ready for review;
M1 remains unstarted and requires the user's approval.
