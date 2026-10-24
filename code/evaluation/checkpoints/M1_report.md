# M1 — Evidence ingestion and normalization — PASS

Date: 2026-10-24. Base: verified M0 `89550259fa6c77e97c4a7bd47cfd65bcb37893a4`.
This report is committed with the M1 implementation.

## Implementation and scope

- `code/ingest/evidence.py`: typed `Observation` and deterministic parsers for
  SQLite SQL, JSON, key/value and structured logs, pipe/plain text and text PDFs;
  participant activity/audit rows; explicit image placeholders; manifest-path
  checks; timezone-aware timestamps; safe in-memory SQLite loading; optional
  source/parser-hash cache. Raw fields, provenance and topology are retained.
- `code/ingest/main.py`: JSONL export and machine-readable coverage, with an
  explicit new output path. `code/ingest/coverage.py` generates the reproducible
  [94-entry coverage report](M1_COVERAGE.md).
- `code/ingest/tests/test_evidence.py`: ten M1 tests, including hand-checked
  synthetic SQL, JSON, log and pipe-text facts and a real text PDF fact, file
  inventory, SQL row counts, cache equality, time/provenance, contradictory
  snapshots, unknown fields, path escape and SQL attachment denial.
- `code/ingest/README.md`: exact commands and normalization contract.
  `code/main.py` remains the M0 stub and has no evaluation import.

There is no identity graph, deletion-intent classifier, policy engine, or
case-decision logic in M1. Source observations with the same resource ID remain
separate. A source record timestamp is never substituted for the manifest's
capture time.

## Coverage and integrity evidence

`python3 code/ingest/coverage.py > code/evaluation/checkpoints/M1_COVERAGE.md`
produces 94/94 manifest entries: 83 parsed files and 11 PNGs marked
`needs_multimodal`. The formats are 24 SQL, 28 JSON, 26 log, 1 text, 4 PDF and
11 PNG. No parse failures or unresolved text files. In addition to those files,
the global CSVs contribute 4,011 activity and 306 audit observations.

Total observations: **8,569**. Breakdown: SQL 969, JSON 948, logs 2,211,
text 44, PDF 80, activity 4,011, audit 306. All 24/24 SQL files loaded into
in-memory SQLite. Per-table materialized row counts equal the number of INSERT
statements for every table, including empty tables. SQL observation topology
counts: primary 580, replica 144, regional 174, reporting 51, failover 20.
Table-level tags preserve primary/replica distinctions inside one snapshot.

No file-level capture timestamp disagrees with the manifest. Two JSON record
timestamps are later than their containing file's manifest capture:
`evidence_13` at `$.records[38]` and `evidence_36` at `$.records[45]`.
Both are retained with their separate timestamps and flagged in coverage;
M1 makes no assumption about which timestamp is authoritative for state.

The canonical observation JSONL SHA-256 is
`8d69c0b4dc573200ad89ad970f337e196b6124e6eed465b3030fb21152d0aeec`.
Two independent coverage runs produced the same report SHA-256,
`e434096c2a97ef2580d20c78a28f92827164298a29f7bbd99c781c35e2202c30`.
Cold and warm cache observations compare equal in the integration test.

## May reference comparison

The ignored May clones were inspected at the pinned commits below; no May
repository was modified or retested for this milestone.

| Reference | Verified source | October adaptation |
|---|---|---|
| Saai `fadb4f24e36d860a9ce4d5155bb30568df80ea4b` | `benchmarks/saai-winner/code/ingest/parser.py`, `code/ingest/chunker.py` | Format-aware parsing and provenance carry over. October preserves SQL records, JSON objects and complete log lines with exact locators; markdown heading/token chunking would fragment identifiers and is omitted. |
| Trenton `c5c765749c1f40469fc3a0c79bfa3ba01085df79` | `benchmarks/trenton/code/agent/embeddings.py:69-74` (`chunk_hash`) | Content SHA-256 caching carries over, with parser-source and manifest hashes added so extraction changes invalidate cached observations. No embeddings or semantic top-k are used. |
| LeeRenJie `94ed9d6e93b566b1b22c30b910da8319448298ff` | `benchmarks/leerenjie/code/main.py:103-132,231-234`, `code/tests/test_verifier.py` | Typed stage traces and offline tests inform explicit observation provenance and fixture tests. October performs deterministic local parsing with no model gate or ranked article retrieval. |

## Tests and known limits

Command: `/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests`.
Result: **93 passed in 1.77s**, zero failures/skips (83 M0, ten M1).
The M1 suite blocks socket connections. M0's sample validator, scorer and
full-size placeholder checks remain passing. `git diff --check` passed.

PDFs are represented by extracted text lines; interpreting layout, image-only
PDFs and screenshots remains later work. JSON nested payloads retain both
original strings and parsed forms where present. `system_id`, `resource_id`,
`data_category` and `state` stay unknown when the source does not state them.
The current identifier forms include exact strings and useful case-folded
email, normalised phone and unchanged hash forms; complete identity linking
belongs to M2. Parser results are not evidence of a resource's current state
at a particular case cutoff, and no semantic top-k filtering occurs.

## Recommendation: PASS

M1-1 through M1-6 are met: complete manifest accounting, 24 SQL loads and row
checks, format fixtures, preserved capture metadata with discrepancies listed,
deterministic offline parsing, and inert handling of untrusted source text.
The M0 suite passes. Stop at M1 pending independent review.
