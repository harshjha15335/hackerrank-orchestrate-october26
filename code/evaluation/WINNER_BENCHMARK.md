# Winner Benchmark: May 2026 References vs. October 2026 "Ghost Data Still Exists"

Audit date: 2026-10-24. Scope: source-level benchmark only. The October implementation has not started.

## 0. Read this first: the domains differ

The four May 2026 repositories solve **Multi-Domain Support Triage**: about 29 tickets go in, and each gets a free-text reply, a `replied`/`escalated` status, a `product_area` and a `request_type`, grounded in a Markdown help-centre corpus. October asks for something structurally different:

| Dimension | May 2026 (support triage) | October 2026 (deletion audit) |
|---|---|---|
| Volume | ~29 eval tickets, 10 samples | **518** eval cases, 32 samples |
| Evidence | ~homogeneous Markdown articles | 94 files: SQL snapshots (replica topologies), JSON bundles, key=value logs, pipe-delimited text, **PDFs, PNG screenshots**, plus 4,011 activity rows, 306 identity-audit rows |
| Retrieval target | "most relevant article" (fuzzy, semantic) | **exact identifiers** (emails in any case, email hashes, phones, `user_id`, `resource_id`) across current *and historical* identities |
| Time | none | each case has an `audit_at` cutoff; evidence after it must be ignored; workflow results are claims |
| Output | 1 label set + prose | ordered `steps_json` array (15 operation types, 3 phases, exact `evidence_id`) |
| Grading | label accuracy + judged prose | case status, step set, field values, **sequence order**, evidence IDs |

So retrieval and generation techniques from May mostly don't carry over. What does carry over is the engineering discipline around them: deterministic guardrails, citation validation, caching, schema enforcement, traces and test harnesses. The rest of this document reads every May technique through that lens.

## 1. Sources and inspected commits

Clones live in `benchmarks/` (git-ignored, `chmod -R a-w` to keep them read-only). Nothing in them was modified. The test runs in §6 used copies in a scratch directory outside the repo.

| Alias | Repository | Inspected commit | Commit date | Stack (from source) |
|---|---|---|---|---|
| **saai** | https://github.com/saai-syvendra/hackerrank-orchestrate | `fadb4f24e36d860a9ce4d5155bb30568df80ea4b` | 2026-05-25 | LangChain `create_agent`, Claude Sonnet + Haiku, OpenAI embeddings, Cohere rerank, LanceDB |
| **trenton** | https://github.com/tmcfarlane/hackerrank-orchestrate-may26 | `c5c765749c1f40469fc3a0c79bfa3ba01085df79` | 2026-05-02 | Raw Anthropic SDK tool loop, BM25 (+ optional Cohere embed/rerank), Cloudflare AI Gateway failover |
| **leerenjie** | https://github.com/LeeRenJie/hackerrank-orchestrate-may26 | `94ed9d6e93b566b1b22c30b910da8319448298ff` | 2026-05-02 | Staged pipeline (triage → retrieve → decide → draft → verify), sentence-transformers, Anthropic Citations API, multi-model consensus judge |
| **amogh** | https://github.com/Amoghk04/hackerrank-orchestrate-may26 | `54f1b0c991e0e8091815c4169f22d31cda749d7a` | 2026-05-15 | Regex classifier + BM25/MiniLM hybrid + single forced-tool Claude call |

### README claims we did NOT verify

- saai `README.md` says the repo won **1st place** out of "12,885 registrations". We didn't check the leaderboard. Treat it as the author's claim.
- Accuracy numbers, cost figures and "deterministic" claims in any README or design doc (`trenton/docs/*`, `leerenjie/PRD.md`, `amogh/design_doc.md`) were **not** reproduced. We didn't run the May agents end-to-end: that needs paid API keys and the May hidden labels.
- Only the observations in §6 were independently executed.

## 2. Source-verified observations by dimension

Every path below is relative to that repo's root at the commit above, and was opened and read during this audit.

### 2.1 Architecture and agent orchestration

| Repo | Observation | Source |
|---|---|---|
| saai | **One agent, one tool.** A LangChain `create_agent` with a single read-only `support_kb` tool that has three modes (`search` / `read` / `grep`), structured output through `ToolStrategy(SupportTicketDecision)`, and two middlewares. | `code/agent/builder.py:39-60`, `code/retrieval/kb_tool.py:57-135` |
| saai | **Cheap rules run before any model call.** `empty → pleasantry → out_of_scope → prompt_injection → too_vague`, then a canned decision. Haiku is used only to label `product_area` on short-circuited rows. | `code/runner/pipeline.py:196-240`, `code/agent/classifier.py:80-121` |
| trenton | Hand-written Anthropic tool-use loop, capped at `MAX_AGENT_TURNS = 3`. The tool validates `company`/`product_area` against allow-lists and returns `is_error` tool results so the model can self-correct. | `code/agent/pipeline.py:37`, `:231-381` |
| leerenjie | **Staged pipeline with a pure, LLM-free decision function.** `triage()` (regex) → `Retriever.retrieve()` → `decide()` (pure) → `draft()` → `verify()`. Each stage writes a typed `TraceRecord`. | `code/main.py:101-228`, `code/decider.py:87-166` |
| amogh | A five-layer linear pipeline. The rule gate can force `escalated`, and a post-hoc override enforces it even when the LLM disagrees. | `code/agent.py:264-359`, `code/agent.py` (force_escalate override inside `_call_claude`) |

### 2.2 Data ingestion and indexing

| Repo | Observation | Source |
|---|---|---|
| saai | Frontmatter parser handling three dialects; heading- and table-aware chunker that never splits inside `<table>`; embedding batches retried with exponential backoff. | `code/ingest/parser.py:1-30`, `code/ingest/chunker.py:1-25`, `code/ingest/builder.py:56-72` |
| trenton | Chunks by H2 section (HR/Claude) or whole file (Visa). Corpus embeddings are cached on disk under `sha256(chunk.text)`, so a path rename doesn't invalidate the cache. | `code/agent/loader.py:1-40`, `code/agent/embeddings.py:69-74` |
| leerenjie | Per-domain pickled BM25 and dense matrices, loaded lazily. | `code/retriever.py:38-64` |
| amogh | Index cache invalidated by an **mtime+size** fingerprint (fragile across clones), stored as pickles. | `code/retriever.py:291-300`, `:307-355` |

### 2.3 Keyword, semantic and hybrid retrieval

| Repo | Observation | Source |
|---|---|---|
| saai | BM25 (LanceDB FTS) + dense vectors, fused with **weighted RRF** (0.3 / 0.7, k=60) with a deterministic tie-break on `chunk_id`, then optional Cohere rerank. Rerank disables itself for the whole process after the first failure. | `code/retrieval/search.py:103-120`, `:123-166`, `code/config.py` (`RRF_K`, `HYBRID_*_WEIGHT`) |
| saai | A `grep` mode for literal identifiers that "semantic search might paraphrase away". This is the May idea closest to what October needs. | `code/retrieval/kb_tool.py:124-133`, `code/retrieval/reader.py:56-90` |
| trenton | BM25 per (company, product_area) bucket by default. The hybrid mode uses RRF with the identity key `(path, anchor)`, and the tie-break is insertion order. | `code/agent/retriever.py:48-109`, `:246-270` |
| leerenjie | BM25 + MiniLM dense → RRF → cross-encoder rerank, with a sigmoid-normalised score used as a confidence threshold. If dense fails it falls back to BM25 only. | `code/retriever.py:16-22`, `:73-157` |
| amogh | Computes RRF over **every** chunk, multiplies by a domain boost (`1.3`), and uses an absolute confidence floor of `0.004`. | `code/retriever.py:237-282`, `code/utils.py:56`, `:63` |

### 2.4 Evidence grounding and citation validation

| Repo | Observation | Source |
|---|---|---|
| saai | **Citation guard.** A path survives in `cited_paths` only if the agent actually called `read` on it during that turn. Unread citations are dropped and recorded in `_dropped_citations`. A reply with no read at all is downgraded to an escalation. | `code/agent/middleware/citation_guard.py:15-72`, called at `code/runner/pipeline.py:306` |
| trenton | A `replied` row with `retrieval_count == 0` is forced to `escalated`. | `code/agent/pipeline.py:107-118` |
| leerenjie | Anthropic **Citations API** (`"citations": {"enabled": True}` on document blocks), then a tiered verifier: Jaccard overlap first (free), with an LLM faithfulness gate only when risk flags are set or retrieval confidence is low. | `code/drafter.py:75-92`, `code/verifier.py:39-82` |
| leerenjie | Multi-model consensus judge: two graders, plus an arbiter that runs only when they disagree (`agree_delta=0.25`). | `code/consensus.py:1-50`, `:364` |
| amogh | **Anti-pattern:** the low-confidence prompt tells the model to "rely on general product knowledge where documents are insufficient", which invites ungrounded output. | `code/agent.py:428` |

### 2.5 Classification and deterministic guardrails

| Repo | Observation | Source |
|---|---|---|
| saai | Regex pre-filters with tight word-count limits, so long tickets never short-circuit. | `code/runner/pipeline.py` (`_pleasantry`, `_too_vague`), lines 1-80 of that file |
| leerenjie | `decide()` is a **pure function with no LLM call**. Forced-escalation precedence, then confidence gates, then the default. Domain policy is declared in YAML and kept in sync with the regex tables. | `code/decider.py:87-166`, `code/policy/risk.yaml` |
| amogh | Regex adversarial detector and request-type classifier, each with its own unit tests. | `code/classifier.py:120-341`, `code/test_classifier.py` |

### 2.6 Output schema validation

| Repo | Observation | Source |
|---|---|---|
| saai | A Pydantic `SupportTicketDecision` with `Literal` enums is the structured-output target, plus `_coerce_decision()` that clamps any unknown enum to a safe default. | `code/schema.py:1-50`, `code/runner/pipeline.py:153-175` |
| amogh | `tool_choice={"type":"any"}` forces a tool call, the result is validated with Pydantic validators, and the call is retried once on failure. | `code/agent.py:32-60`, `:466-470` |
| leerenjie | **A post-run whole-file validator**: column order, enum membership, cross-field invariants (an escalated row has an empty area). It also asserts an *escalation-rate band of 5-50%*, which is a distribution heuristic, not a correctness rule. | `code/main.py:374-417` |

### 2.7 Evaluation methodology and test coverage

| Repo | Observation | Source |
|---|---|---|
| saai | Per-column diff against the 10-row sample, plus diagnostics (response length, cited-but-unread paths taken from the trace dir). No unit tests. | `code/runner/eval_sample.py:33-157` |
| trenton | The scorer separates **true gold** (sample CSV) from **provisional gold** (hand labels, explicitly "NOT ground truth"), and keeps a documented-divergence list. A separate retrieval scorer measures recall@k across ablations (BM25, hybrid, rerank). No unit tests. | `code/eval/scorer.py:1-60`, `code/eval/retrieval_scorer.py:141-330` |
| leerenjie | **160 offline unit tests** across 12 files, using fake LLM clients (dependency injection through `haiku_call`), plus a CSV of adversarial fixtures. | `code/tests/*.py`, `code/tests/adversarial_tickets.csv`, `code/verifier.py:36-75` |
| amogh | 57 classifier unit tests and a positional sample evaluator with a 70% pass bar. | `code/test_classifier.py`, `code/evaluate.py:73-120` |

### 2.8 Caching, token efficiency and fault tolerance

| Repo | Observation | Source |
|---|---|---|
| saai | `cache_control: ephemeral` on the static system prompt. Query embeddings and rerank scores are disk-cached by SHA-256 key, with atomic `tmp → replace` writes. The Haiku classifier is cached by content hash. | `code/agent/builder.py:20-36`, `code/retrieval/search.py:38-83`, `code/agent/classifier.py:42-68` |
| trenton | Retry only on transient errors (timeouts, 502/503/504) with exponential backoff, while 4xx errors fail fast. **Sticky failover** from the gateway to the direct API. | `code/agent/pipeline.py:40-55`, `:183-219`, `code/agent/failover.py` |
| leerenjie | A generic **SHA-keyed request→response disk cache** keyed on the full canonical payload, so identical reruns cost nothing. | `code/cache.py:1-29`, used in `code/consensus.py` and `code/drafter.py` |
| all | Per-row exception handling degrades the row to a safe default and lets the batch continue. | saai `pipeline.py` agent-error branch, trenton `main.py:69-82`, leerenjie `main.py:202-210`, amogh `agent.py` `_safe_fallback` |

### 2.9 Observability and debugging

| Repo | Observation | Source |
|---|---|---|
| saai | A per-row JSON trace (`pathway`, tool trace, decision, elapsed) under a timestamped run directory. A live tool-call callback drives the TUI. A `--row N` flag runs a single case. | `code/runner/pipeline.py:317-338`, `code/retrieval/kb_tool.py:22-54`, `code/main.py` |
| leerenjie | `runs/trace.jsonl` with one structured record per stage. A `query` sub-command prints a full pipeline trace for a single input. | `code/main.py:231-234`, `:309-371` |
| amogh | Writes the pipeline trace as JSON **into the user-facing `justification` field**. That makes debugging easier but pollutes the output. | `code/agent.py` (pipeline_trace prepend in `_call_claude`) |

### 2.10 Security and prompt-injection resistance

| Repo | Observation | Source |
|---|---|---|
| saai | A multilingual regex injection detector (EN/FR/ES/DE) runs **before** the model, short-circuits with a fixed refusal, and is duplicated as middleware. A sandboxed reader rejects `..` and symlink escapes outside `data/`. | `code/agent/middleware/prompt_injection.py:14-66`, `code/retrieval/reader.py:13-32` |
| leerenjie | **Spotlighting:** user text is wrapped in `<USER_TICKET>` tags and the closing tag is escaped. | `code/drafter.py:94-97` |
| trenton | Prompt-only defence (instructions in the system prompt). | `code/agent/prompts.py:113`, `:328` |
| repo hygiene | trenton commits `code/.cache/embeddings.npy` (14 MB) and a nested `submission_code.zip`. October's rules reject nested archives in `code.zip`. | `git ls-files` in trenton; `.gitignore:33` |

## 3. Techniques worth adapting for October

Ranked by expected impact on October scoring. For each one: what to take, and how it changes for October.

1. **A pure, deterministic decision core** (leerenjie `decider.py`). October's status, policy action, step set and order are all functions of the evidence. Build `decide_case(case, observations, rules) -> steps` as a pure function. Use the LLM only where determinism is impossible (multilingual intent, screenshot reading). This also gives us the determinism §6.7 asks for.
2. **Cite-only-what-you-verified** (saai `citation_guard.py`). October version: an `evidence_id` survives only if (a) the parser extracted an observation from that exact `file_id` / `activity_id` / `audit_id`, (b) that observation names the cited `resource_id` and a resolved identifier of the subject, (c) `captured_at <= audit_at`, and (d) the observed state supports the step's operation. Anything else is dropped and logged in `_dropped_evidence`.
3. **Literal / grep retrieval over identifiers** (saai `grep` mode). This becomes the *primary* retrieval in October: an inverted index from normalised identifier → (file_id, locator, resource_id, captured_at). Normalising means lower-casing emails, digit-only phones, and treating hashes as-is.
4. **Pre-LLM rule layer with a cached small-model fallback** (saai `pipeline.py:196-240` + `classifier.py`). Use it for deletion-intent classification: deterministic patterns catch the ~500 boilerplate deletion requests, and the model is called only for texts the rules can't settle. The cache is keyed by `sha256(text)`. Negation-aware rules are mandatory (see §5).
5. **SHA-keyed, atomic disk cache for every model call** (leerenjie `cache.py` + saai `_save_json` tmp→replace). Key on (model, prompt-version, input-hash). This makes the 518-case run repeatable, cheap to re-run, and directly measurable for `usage_report.md`.
6. **Prompt caching of the static prefix** (saai `builder.py:20-36`, trenton `pipeline.py:68-74`). Rules, the operation table and few-shot *format* examples go in one cached prefix.
7. **Transient-only retry plus fail-fast on 4xx** (trenton `pipeline.py:183-219`), and per-row isolation so the batch keeps going. October change: a failed model call must fall back to a **deterministic** answer, never to a canned status. That can still produce a valid row, flagged in the trace.
8. **Schema-first output** (saai `schema.py` + `_coerce_decision`, leerenjie `cmd_validate`). Pydantic `Step` with `Literal` phase/operation/state, an operation→state map, and a whole-file validator (518 rows, sorted, consecutive `step_no`, phase order, evidence rules). Don't clamp silently: an invalid step is a bug to surface, not to coerce.
9. **Dependency-injected model clients plus offline unit tests** (leerenjie `verifier.py` `haiku_call`, `tests/test_*_clients.py`). Every LLM touch point gets a fake so the full test suite runs with no key.
10. **Honest evaluation bookkeeping** (trenton `eval/scorer.py` gold vs provisional gold; documented divergences). October's `evaluation_report.md` must separate *sample-verified* metrics from metrics on custom cases.
11. **Per-case structured trace plus single-case debug flag** (saai `_write_trace`, `--row`; leerenjie `query`). October version: `python code/main.py --case case_11 --explain` prints the resolved identities, matched observations, the policy rule applied and the evidence for each step.
12. **Spotlighting untrusted text** (leerenjie `_spotlight_ticket`). In October, `request_text` *and every evidence file* are untrusted. Logs and support messages can contain injected instructions.

## 4. Techniques unsuitable for October

| Technique (source) | Why it doesn't fit October |
|---|---|
| Dense embeddings / vector DB as primary retrieval (saai `search.py`, leerenjie `retriever.py`, amogh `retriever.py`) | Matches have to be **exact** on identifiers. Semantic similarity actively pulls in decoys: the data contains near-duplicate people such as `Mateo Ríos` vs `Mateo Rios Gil` in `customer_accounts_failover_replica_20260902.sql`. Embeddings add cost and nondeterminism for no recall gain on 94 files. |
| Cohere / cross-encoder rerank (saai, trenton, leerenjie) | It ranks relevance. October needs set membership (every relevant record, not the top-k). Any top-k cutoff silently drops findings. |
| Free-form agent tool loop per case (saai `create_agent`, trenton tool loop) | 518 cases × multi-turn loops is costly and non-reproducible, and step order and IDs must be exact. The model would be re-deriving deterministic joins. |
| Multi-model consensus faithfulness judge (leerenjie `consensus.py`) | October grounding is checkable mechanically (does file X contain resource Y with state Z?). A probabilistic judge is strictly weaker and multiplies token cost. |
| Distribution-band validators (leerenjie `main.py:408-410`, 5-50% escalation rate) | Status distribution is a property of the hidden data. Tuning towards a band is a form of label fitting. |
| Few-shot built from sample *answers* (leerenjie `few_shot.py`) | Pasting sample outputs into prompts risks the model copying sample `resource_id` / `evidence_id` values into eval cases. That would effectively hardcode public outputs. Use synthetic format examples only. |
| "Rely on general knowledge" fallback (amogh `agent.py:428`) | Violates §6.6: every finding must cite participant-visible evidence. |
| Trace JSON inside the output field (amogh) | October's `steps_json` is graded field by field, so extra content is wrong output. Traces belong in `code/evaluation/runs/`, not in `output.csv`. |
| `code/__init__.py` making `code` a package (leerenjie, amogh) | It shadows Python's stdlib `code` module. Under Python 3.13, pytest's `pdb` import crashes (`module 'code' has no attribute 'InteractiveConsole'`); we reproduced this (§6). October keeps the `code/` folder, so don't add `code/__init__.py`. Run modules by path with a `sys.path` insert, as saai `main.py:17` does. |
| Committed caches and nested zips (trenton) | `code.zip` must not contain nested archives, and caches can carry derived personal data. |
| Absolute RRF-score confidence floors (amogh `utils.py:63` = 0.004, leerenjie sigmoid thresholds) | Uncalibrated. October's "confidence" is binary: an observation either exists or it doesn't. |
| TUI / gateway / OpenRouter plumbing (saai `tui/`, trenton `failover.py` Cloudflare paths) | Out of scope. Adds credentials and surface area without moving the score. |

## 5. Gaps October must solve independently (no May analogue)

All of these were found by profiling `dataset/` during this audit. The numbers come from scripts run against participant-facing files only.

1. **Historical identity resolution.** 403 of 518 request emails match a current identity, and **95 match only a historical email** in `user_audit_log.csv`. Case-insensitive matching over current + historical emails resolves all 518, with 0 ambiguous. The audit log also carries `email_hash` (107) and `phone` (92) changes. Evidence uses varying case (`CHOI.JIHOON94@GMAIL.COM` in `customer_account_handover_20261001.txt`), hashes, phones and `user_id`/`subject_reference`. We need an identity graph per subject: {user_id, every email ever (case-folded), every email_hash, every phone (normalised), names (exact only, low weight)}.
2. **Audit-time reconstruction.** Evidence `captured_at` must be `<= audit_at`. The comparison is inclusive: sample `case_11` cites `evidence_03`, captured at exactly its `audit_at` of `2026-10-01T12:00:00Z`. None of the 32 samples cites later evidence. For each (system_id, resource_id) the latest observation at or before `audit_at` decides the state. `system_activity.csv` (4,011 rows; 721 `FAILED`, 376 `PARTIAL`) is a stream of claims to reconcile, not truth.
3. **Multi-format evidence normalisation into a single observation table.** SQLite-executable SQL with primary/replica/failover tables (replication drift), JSON snapshot bundles, `key=value` logs, pipe-delimited handover text, 4 PDFs (`pdftotext` is available locally) and **11 PNG console screenshots**. Screenshots carry facts that exist nowhere else; for example `search_index_inspector_20260901.png` shows `search_428`, `g.silva76@gmail.com` and `user_13`, plus a near-miss `g.silva76.jr@gmail.com` decoy.
4. **Policy engine over `deletion_rules.csv`.** 15 rules, including conditional ones (support message with shared context → REDACT; attachment belonging only to the subject → DELETE; security log within retention → RETAIN; backup → RETAIN + block restore; ACCOUNT_TOMBSTONE → REDACT direct identifiers but keep `subject_reference`). Mapping each record to a `data_category`, and evaluating the condition, has to come from evidence fields.
5. **Data-flow and restore-risk detection.** `REPORT_ACTIVE_DATA_FLOW` and `REPORT_RESTORE_RISK` depend on sync/connector/backup state at `audit_at` (for example `connector_configurations_20260812.json`, `backup_restore_console_20260429.png`, and `CHECK_DATA_FLOW` / `BLOCK_RESTORE` / `RESTORE_BACKUP` activity).
6. **Deterministic step synthesis and ordering.** In all 32 samples (0 deviations, verified by script), steps sort by **(operation enum index as listed in problem_statement.md, system_id, resource_id)** within phase order. AGENTS.md §6.5 also says "process downstream copies before their source records when the dependency requires it". That never fires in the samples, so treat it as an open risk: implement the pure sort, keep a dependency-override hook, and test it.
7. **Verification coverage semantics.** In INCOMPLETE samples, the VERIFICATION phase covers every relevant resource's required final state. That includes resources that were *already* compliant: `case_11` verifies `account_4248 VERIFY_RECORD_ABSENT` with no matching finding, and it verifies retained records (`VERIFY_RECORD_PRESENT` on `security_service`). All of those carry an empty `evidence_id`. In COMPLETE samples every verification step cites evidence.
8. **Deletion-intent classification with negation traps.** Of the 518 requests, 508 begin with one of 17 boilerplate deletion openings in 6 languages (EN, PT, ES, FR, JA, KO). About 10 are non-deletion and some are adversarial: "please don't delete or change anything", "remove me from marketing lists only", "this is an information request, not a request to erase it". A naive keyword classifier fails both ways. 26 genuine deletion requests (14 PT, 12 FR) contain none of a simple keyword list's roots, and the traps *do* contain "delete"/"erase"/"remove".
9. **Decoys and global noise.** Activity rows and evidence describe unrelated users. One email appears in two separate cases (`ingrid.dahl@outlook.com`), so the state must be computed per case at that case's own `audit_at`.
10. **Required reporting.** `evaluation_report.md` needs case-, step-, field- and sequence-level accuracy plus at least 3 custom cases. `usage_report.md` needs token and cost accounting. No May repo produced metrics at this granularity.

## 6. Independently executed checks (this audit)

| Check | Command (scratch copy, Python 3.13.17) | Result |
|---|---|---|
| leerenjie unit tests | `python -m pytest -q -p no:cacheprovider code/tests` | **INTERNALERROR**: the `code` package shadows the stdlib `code` module (pdb import) |
| leerenjie unit tests, debugger plugin off | `... -p no:debugging code/tests` | **160 passed** in 0.66 s (offline, fake clients) |
| amogh unit tests | `python -m pytest -q -p no:cacheprovider -p no:debugging test_classifier.py` (from `code/`) | **57 passed** in 0.09 s |
| saai / trenton | No unit-test suite in the repo | Not runnable without API keys and the May corpus/labels; **not executed** |
| October sample ordering rule | Script over `dataset/sample_output.csv` | 32/32 cases follow (op-index, system_id, resource_id); 0 evidence captured after `audit_at` |
| October identity coverage | Script over requests + identities + audit log | 518/518 resolvable (403 current, 95 historical-only, 0 ambiguous) |

## 7. Recommended implementation priorities

Ordered by dependency first, then score impact. Milestones and acceptance tests are in `DEVELOPMENT_CHECKPOINTS.md`.

1. **M0 – Contract harness first:** the Pydantic step schema, the whole-file validator, and a sample scorer computing case/step/field/sequence metrics. Every later milestone is measured with it.
2. **M1 – Evidence normalisation:** parsers for SQL (in-memory `sqlite3`), JSON, logs, text and PDFs into one `Observation` table that keeps `file_id`, locator and `captured_at`.
3. **M2 – Identity graph:** current + historical, case-folded emails, hashes and phones, with a per-identifier inverted index (saai's `grep`, done properly).
4. **M3 – Deletion-intent classifier:** negation-aware rules, then a cached LLM fallback for the undecided texts only.
5. **M4 – Audit-time state reconstruction:** latest observation at or before `audit_at` per resource, with activity treated as claims.
6. **M5 – Policy engine:** map each category and condition to a required action, including the tombstone and retention rules.
7. **M6 – Data-flow and restore-risk detection.**
8. **M7 – Step synthesis, ordering and the evidence-citation guard** (the October version of saai's citation guard).
9. **M8 – Multimodal extraction:** screenshot reading with a vision model, run offline and cached by file hash, then merged into the `Observation` table. It sits this late only because M1-M7 must work on text evidence first; its *score* impact may be high, so measure it against the samples.
10. **M9 – Evaluation and usage reports**, with custom adversarial cases.
11. **M10 – Hardening:** fault tolerance, injection-resistance tests, a clean full run and packaging.

The design principle across all of these: **deterministic by default, LLM where perception or language demands it, and every claim checked mechanically against cited evidence.**
