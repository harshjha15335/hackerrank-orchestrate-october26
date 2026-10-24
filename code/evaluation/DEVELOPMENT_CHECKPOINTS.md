# Development Checkpoints: Ghost Data Still Exists (October 2026)

This document defines the milestones, their acceptance tests, and the comparison report each one must produce before the next milestone starts. The reference techniques come from `WINNER_BENCHMARK.md` (May 2026 repos, pinned commits in §1 of that file).

## Global rules (apply to every milestone)

1. **No hardcoded sample answers.** No code path may contain a `case_id`, `resource_id` or `evidence_id` string that appears in `dataset/sample_output.csv`. CI check: `grep` the source tree for every such ID; any hit is a FAIL.
2. **Use only participant data.** Only files under `dataset/` are read. Sample outputs are used only by the scorer, never by prediction code.
3. **Hold-out discipline.** Split the 32 samples into a fixed **dev split** (`case_01`–`case_22`) and a **holdout split** (`case_23`–`case_32`). Tune on dev and report holdout separately. A change that improves dev but lowers holdout is a FAIL unless the report explains why.
4. **Determinism.** Two consecutive runs with a warm cache must produce byte-identical `output.csv` (compare with `sha256sum`).
5. **No regression.** Every milestone re-runs all earlier acceptance tests.
6. **Logging.** Every working session appends to the root `log.txt` per AGENTS.md §5.
7. **May code is a reference, not a source.** Don't copy May code. Each adaptation is re-implemented for October's data and named in the comparison report.

## Comparison report template (required per milestone)

Save as `code/evaluation/checkpoints/M<N>_report.md`. A milestone isn't closed until this file exists and its recommendation is PASS.

```markdown
# M<N> – <title> – Comparison Report
Date / commit: <iso date> / <git sha>

## 1. May reference technique
- Repo + commit: <alias> @ <sha>
- Source file(s): <path:lines>
- What it does (1–3 sentences, from source, not README)

## 2. Our implementation
- Files: <code/...>
- Design summary (what/why)

## 3. Improvements and differences
- <difference> → <reason tied to October data or contract>

## 4. Tests executed and results
| Test ID | Command | Expected | Actual | Status |
|---|---|---|---|---|

Metrics (dev / holdout): <case acc, step F1, field acc, sequence acc, as relevant>

## 5. Known limitations
- <limitation, impact, follow-up milestone>

## 6. Recommendation: PASS | FAIL
Justification: <which acceptance criteria are met / unmet>
```

## Metric definitions (used from M0 onward)

The canonical step key is `(phase, operation, system_id, resource_id)`.

- **Case status accuracy**: share of cases whose `deletion_status` matches.
- **Step precision / recall / F1**: over the multiset of canonical step keys per case, micro-averaged.
- **Field accuracy**: for matched steps, the share of the 7 fields that are equal, reported per field. `evidence_id` is reported separately because it's the hardest field.
- **Sequence accuracy**: share of cases whose full ordered list of canonical keys matches exactly. Also report normalised Kendall-tau on matched steps.
- **Evidence validity rate**: share of non-empty `evidence_id`s that exist in the manifest, `system_activity.csv` or `user_audit_log.csv` *and* were captured or happened at or before `audit_at`.

---

## M0: Contract harness and scorer

**Goal:** make correctness measurable before any logic exists.
**May reference:** saai `code/schema.py` + `_coerce_decision` (`code/runner/pipeline.py:153`); leerenjie `cmd_validate` (`code/main.py:374-417`); saai `code/runner/eval_sample.py`.

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M0-1 | Validate `dataset/sample_output.csv` with our validator | 32/32 rows valid |
| M0-2 | Mutation suite: wrong operation→state pair, gap in `step_no`, phase out of order, unknown operation, non-empty evidence on REMEDIATION, empty evidence on a COMPLETE verification step, unsorted rows, missing row, extra key in a step | Every mutation rejected, with a specific message |
| M0-3 | Scorer self-test: score `sample_output.csv` against itself | All metrics = 1.0 |
| M0-4 | Scorer sensitivity: drop one step, swap two steps, change one `evidence_id` | Recall, sequence and field metrics each drop by the expected amount |
| M0-5 | Stub `code/main.py` writes 518 `NOT_APPLICABLE,[]` rows | Validator passes; row count 518; sorted by `case_id` |
| M0-6 | No `code/__init__.py`; pytest runs without `-p no:debugging` | Suite collects and runs on Python ≥3.11 |

Adapt saai's typed enums, but **fail loudly**: no silent coercion like saai's `_coerce_decision`. Don't adopt leerenjie's distribution band.

## M1: Evidence ingestion and normalisation

**Goal:** turn all 94 manifest files plus the activity and audit CSVs into one `Observation` table: `(evidence_id, locator, captured_at, system_id, resource_id, data_category?, state?, identifiers[], raw_fields)`.
**May reference:** saai `code/ingest/parser.py`, `code/ingest/chunker.py` (format-aware, table-preserving parsing); trenton `code/agent/embeddings.py:69` (content-hash cache identity).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M1-1 | Coverage: every `file_id` in `evidence_files.csv` is parsed or explicitly marked `needs_multimodal` (images until M8) | 94/94 accounted for; 0 crashes |
| M1-2 | SQL: every `.sql` loads into in-memory `sqlite3`; every table becomes rows with a topology tag (primary / replica / failover / regional / reporting) | 24/24 files load; row counts equal `INSERT` counts |
| M1-3 | Golden extraction fixtures: 1 hand-checked fixture per format (SQL, JSON bundle, key=value log, pipe text, PDF) with the expected observations | Exact match |
| M1-4 | `captured_at` is taken from the manifest; mismatches with in-file timestamps are logged | Report lists the discrepancies (expect 0 or a justified list) |
| M1-5 | Parsing is deterministic and offline | Two runs give an identical observation hash; no network calls (socket blocked in test) |
| M1-6 | Untrusted content: text like "ignore previous instructions" inside evidence is stored as data only | Fixture shows it as a plain field; no control-flow change |

## M2: Identity graph (current + historical)

**Goal:** resolve each request email to a subject `user_id` and that subject's full identifier set *as of `audit_at`*.
**May reference:** saai `grep` mode (`code/retrieval/kb_tool.py:124-133`), the literal-identifier insight; amogh `infer_company` (`code/classifier.py:166`) as a weak analogue. No May repo does entity resolution, so this is a gap.

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M2-1 | Resolve all 518 request emails (case-insensitive, current ∪ historical) | 518/518 resolved; 0 ambiguous. If ambiguous, the case is flagged, not guessed |
| M2-2 | Historical-only emails resolve to the right `user_id` | Recount current-email membership from `user_identities.csv` against `deletion_requests.csv`; the current dataset has 100 historical-only request rows (418 current matches among 518). Resolve all independently counted rows, with 10 transitions traced through `user_audit_log.csv`. |
| M2-3 | Identifier set includes every historical email, `email_hash` and phone (normalised) | Unit fixtures for each `field_name` type |
| M2-4 (original; report alongside revised gate) | Inverted index: identifier → observations | Every sample-cited (resource, evidence) pair for dev cases is reachable from that subject's identifiers (recall = 1.0 on dev). This conflates existing records with scoped evidence of absence; retain the fraction and do not claim it passed. |
| M2-4R (revised evidence-safe gate) | Identity retrieval and negative-evidence scope accounting | 100% of citations with a source-backed identity join are retrieved; 100% of cited SQL absence snapshots expose table scope separately without assigning a missing resource to a subject; every remaining citation has source/locator and join diagnostics as unattributed; adversarial fixtures yield zero unsupported cross-record correlations. Unattributed citations do not count as identity hits or proof of an absent state. |
| M2-5 | Decoy rejection: near-miss emails (e.g. `x.jr@` vs `x@`) and same-name different people don't link | Fixture set of ≥5 decoys: 0 false links |
| M2-6 | Duplicate-subject cases (same email, 2 cases) are computed independently | Both cases resolve; their states differ only through `audit_at` |

## M3: Deletion-intent classification

**Goal:** decide `NOT_APPLICABLE` correctly in every language, including negation traps.
**May reference:** saai pre-LLM rule cascade (`code/runner/pipeline.py:196-240`) + cached Haiku classifier (`code/agent/classifier.py`); saai multilingual regex (`code/agent/middleware/prompt_injection.py`); leerenjie spotlighting (`code/drafter.py:94`).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M3-1 | All 32 samples classified as deletion-authorising | 32/32 |
| M3-2 | Custom trap set (≥15 texts written by us, not copied from eval rows): access, export, correction, marketing opt-out, "don't delete", "not a request to erase", multi-language deletions, injected instructions | 100% correct |
| M3-3 | Full eval run distribution report: count of NOT_APPLICABLE and the list of texts routed to the LLM | Every LLM-routed text listed with its decision; reviewer agrees on manual audit |
| M3-4 | Cache: re-run makes 0 model calls | Call counter = 0 on second run |
| M3-5 | Offline fallback: with no API key, the classifier still returns a decision (rules only) and marks it `degraded` | Valid output; degraded count reported |

## M4: Audit-time state reconstruction

**Goal:** for each (system_id, resource_id) linked to the subject, determine the state at `audit_at`.
**May reference:** none. Nearest analogue: trenton's "workflow contract" override (`code/agent/pipeline.py:107-118`), which also refuses to trust a claimed outcome without evidence.

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M4-1 | No observation with `captured_at > audit_at` influences any case (inclusive boundary) | Property test over all cases: 0 violations |
| M4-2 | Latest-observation-wins per resource; ties broken deterministically (e.g. evidence type priority, then `evidence_id`) | Fixtures: resource deleted then resynced → PRESENT; present then deleted → ABSENT |
| M4-3 | Activity `reported_result=SUCCESS` without a corroborating observation doesn't set ABSENT | Fixture passes |
| M4-4 | Replica drift: primary ABSENT, replica PRESENT → replica reported | Fixture from a real SQL topology passes |
| M4-5 | Dev-split status accuracy (with M5 stubbed as DELETE-all) | Reported. No threshold; this is a baseline |

## M5: Policy engine

**Goal:** apply `deletion_rules.csv` (15 rules) to every relevant record, including conditions, retention and tombstones.
**May reference:** leerenjie pure `decide()` (`code/decider.py:87-166`) + declarative `code/policy/risk.yaml`.

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M5-1 | Rules loaded from CSV at runtime; no rule text duplicated in code | Changing a rule's action in a temp copy changes the output |
| M5-2 | Per-category fixtures: each of the 15 rules with condition true/false | 100% |
| M5-3 | Tombstone: `subject_reference` kept, name/email/phone/email_hash must be null → otherwise `REPORT_EXPOSED_PII` + `REDACT_RECORD` | Fixture from `customer_data_snapshot_bundle_*.json` passes |
| M5-4 | Retained records (security audit, legal hold, backups) are never DELETE'd; they get `VERIFY_RECORD_PRESENT` | 0 DELETE steps on RETAIN categories across the full run |
| M5-5 | Dev-split metrics | Status accuracy and step F1 reported; target ≥ 0.80 step F1 on dev before M6 |

## M6: Active data flows and restore risks

**Goal:** detect `REPORT_ACTIVE_DATA_FLOW` and `REPORT_RESTORE_RISK` and plan `DISABLE_DATA_FLOW` / `BLOCK_RESTORE`.
**May reference:** none (gap).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M6-1 | Flow is ACTIVE at `audit_at` only if the latest flow evidence ≤ `audit_at` says enabled/active and it carries the subject's data | Fixtures: enabled → disabled → enabled timeline evaluated at 3 cut-offs |
| M6-2 | Backup with restore access not blocked → restore risk; blocked → `VERIFY_RESTORE_BLOCKED` only | Fixture passes |
| M6-3 | Dev-split recall on flow and restore steps | = 1.0, or every miss explained |

## M7: Step synthesis, ordering and evidence-citation guard

**Goal:** emit the exact `steps_json`: findings → remediation → verification, ordered by (operation enum index, system_id, resource_id), with validated evidence.
**May reference:** saai citation guard (`code/agent/middleware/citation_guard.py:15-72`), "cite only what you actually read"; leerenjie tiered verifier (`code/verifier.py`).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M7-1 | Ordering: re-emit sample steps from their canonical keys | 32/32 sequence-identical |
| M7-2 | Dependency hook: a fixture where a downstream copy depends on a source (AGENTS.md §6.5) | The hook reorders only when the dependency is evidenced; samples stay 32/32 |
| M7-3 | Citation guard: every non-empty `evidence_id` names an observation that mentions the step's `resource_id` and a subject identifier, captured ≤ `audit_at` | Evidence validity rate = 100%; dropped citations logged |
| M7-4 | COMPLETE ⇒ only VERIFICATION steps, all with evidence. INCOMPLETE ⇒ remediation and verification have empty evidence; verification covers *all* relevant resources (including already-compliant and retained ones) | Validator passes; dev-split coverage matches samples |
| M7-5 | Dev and holdout metrics | Report case acc, step F1, field acc (per field), sequence acc. Target: holdout case acc ≥ 0.90 and sequence acc ≥ 0.75 |

## M8: Multimodal evidence (images, scanned PDFs)

**Goal:** extract structured facts (resource IDs, identifiers, states, timestamps) from the 11 PNG screenshots and any PDF text that `pdftotext` can't read, and merge them into the M1 table.
**May reference:** none for vision. Caching follows saai `code/agent/classifier.py:42-121` (content-hash disk cache) and leerenjie `code/cache.py`.

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M8-1 | Structured-output schema for image extraction (JSON); responses validated, retried once | 11/11 images yield valid JSON |
| M8-2 | Hand-checked golden facts for ≥4 screenshots (e.g. `search_index_inspector_20260901.png`: `search_428` ↔ `g.silva76@gmail.com` ↔ `user_13`; decoy `search_1874` is not linked) | 100% field match on goldens |
| M8-3 | Cache by `sha256(file bytes) + prompt_version + model`; second run makes 0 vision calls | Counter = 0 |
| M8-4 | Extracted text is treated as untrusted data | Injection fixture image: no behaviour change |
| M8-5 | Ablation: dev and holdout metrics with and without image observations | Report the delta; keep only if it doesn't lower holdout |

## M9: Evaluation and usage reports

**Goal:** produce `code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md` per AGENTS.md §6.8.
**May reference:** trenton `code/eval/scorer.py` (true vs provisional gold, documented divergences) and `code/eval/retrieval_scorer.py` (recall@k ablations); saai `code/runner/eval_sample.py` (diagnostics from traces).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M9-1 | Report contains case, step, field and sequence accuracy for dev, holdout and all 32 | Present, generated by script (not hand-typed) |
| M9-2 | ≥3 custom cases (target 8): historical-email-only, tombstone with leaked PII, sync recreation after delete, evidence after `audit_at` (must be ignored), non-deletion trap, injection in evidence, replica drift, backup restore risk | Each has input, expected output, actual output and PASS/FAIL |
| M9-3 | Failures-and-improvements section lists each fixed failure with before/after metrics | Present |
| M9-4 | Usage report from the real final run's call ledger: provider, model, calls, input/output tokens, total and average per request, estimated cost per model and overall | Numbers reconcile with the ledger file |
| M9-5 | Claims hygiene: every metric in the reports traces to a command output | Reviewer can reproduce each number |

## M10: Hardening, full run and packaging

**May reference:** trenton transient-only retry + fail-fast (`code/agent/pipeline.py:183-219`); per-row isolation (all four repos); saai per-row JSON trace (`code/runner/pipeline.py:317`).

| ID | Acceptance test | Pass criterion |
|---|---|---|
| M10-1 | Clean run (cache cleared) processes 518 cases | 518 valid rows, root `output.csv`, validator PASS |
| M10-2 | Fault injection: model client raising a timeout or 5xx for 20% of calls | Run completes; affected cases fall back deterministically and are listed |
| M10-3 | 4xx / auth error fails fast with a clear message (not 518 silent fallbacks) | Exit non-zero with a diagnostic |
| M10-4 | Determinism: two warm runs give byte-identical output | `sha256sum` equal |
| M10-5 | Per-case trace: `--case <id> --explain` shows identities, observations, rules, ordering and evidence | Works for any case |
| M10-6 | Secrets and packaging: no keys in the repo or `log.txt`; `code.zip` has no `dataset/`, caches, venvs or nested archives; README has setup and run instructions | Packaging script check passes |

## Sign-off sequence

M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → (M8 ablation) → M9 → M10. A milestone may start early only if its inputs are stable. It closes only with a PASS report.
