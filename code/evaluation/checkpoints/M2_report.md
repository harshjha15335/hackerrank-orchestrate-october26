# M2 — Historical identity resolution — FAIL (retrieval gate)

Date: 2026-10-24. Base: `main` at
`644cb488c85e7082b6b49789edc8f8ba662905c5`.

## Implementation

- `code/identity/graph.py`: time-scoped current and historical identity graph.
  Reverses post-cutoff changes, preserves original and normalized values, and
  returns `resolved`, `unresolved`, or `ambiguous` without guessing.
- `code/identity/retrieval.py`: exact identifier postings and source-scoped
  correlation through trace IDs, JSON export row positions, and PDF document
  references. Returns all candidates with direct/context/correlated strength,
  full observation provenance, and an inclusive aware-datetime cutoff.
- `code/identity/main.py` and `README.md`: single-case inspection CLI without
  audit decisions. `code/main.py` remains the M0 stub and reads no gold.
- `code/ingest/evidence.py`: aware-datetime discrepancy check and a separate
  document-scoped PDF reference where the resource and identifier occur on
  different lines. Existing line observations are preserved.
- `code/identity/tests/test_graph.py` and
  `code/evaluation/tests/test_m2_recall.py`: synthetic history/decoy/ambiguity
  and retrieval tests; only evaluation tests read sample answers.

## Results against M2 acceptance tests

| Gate | Result |
|---|---|
| M2-1 | 518/518 requests resolved; 0 ambiguous, 0 unresolved. Ambiguity is surfaced by a synthetic collision test. |
| M2-2 | **100** historical-only request rows resolve. An independent recount finds 418/518 request emails in the current 850-row identity CSV and 100 absent from it but linked by audit history. The earlier checkpoint estimate of 95 is stale; ten historical cases were traced to email `old_value` transitions in tests. |
| M2-3 | Synthetic tests cover successive email changes, case-insensitive email, digit-normalized phone and exact opaque hash; future values are excluded from earlier views. Original strings and audit IDs remain available. |
| M2-4 | **31/38 dev-sample cited evidence/resource pairs reachable (81.6%)**. Seven remain unsupported by an identifier link; this required 100% gate fails. |
| M2-5 | Five near-email decoys and a same-name second user yield zero false identity links. Records with multiple direct identities are labelled `mixed_context`. |
| M2-6 | Two cases for the same subject at different cutoffs retain distinct current identity views. |

The seven misses are in six case contexts and involve four kinds of evidence:
three SQL absence citations to the failover snapshot; one JSON analytics row
with null identifiers; one log lookup with null identifiers; and two service
export rows with null identifiers. The SQL citation for one account resource
has no occurrence of that resource ID anywhere in the participant evidence.
There is no evidence-grounded join from its user to that absent row. The
others likewise cannot safely be attributed by email, hash, phone, stable ID,
trace ID or document context at M2. M1 retains their raw data; no additional
parsing can recover a field that the source does not contain. The evaluation
test characterizes 31/38 without embedding sample answer IDs in source.

`record_time > captured_at` now compares parsed aware datetimes. Synthetic
positive and negative offset tests demonstrate both directions where string
ordering would be wrong. The same two real-data discrepancies remain in the
regenerated M1 coverage; no manifest or record timestamp was rewritten.

The current coverage has 94/94 manifest files and **8,570** observations,
including one document-scoped PDF reference added to preserve separated text
context. Canonical observation hash:
`da9b491dce3119cd8b1d77ddf58604112773168a43e14993ef3551896d3e8dd0`.

## Verification and determinism

`/tmp/m0-venv/bin/python -m pytest -q -p no:cacheprovider
code/evaluation/tests code/ingest/tests code/identity/tests`:
**107 passed in 5.58s**, zero failures/skips. The original M0 and M1 suites
passed within that run. Tests block socket connections, check exact case
cutoffs, and compare repeated retrieval digests. The ingestion coverage report
can be regenerated with `python3 code/ingest/coverage.py`.
Two separate `python3 code/identity/main.py --case case_33` runs produced
byte-identical JSON, SHA-256
`537325544f18012671071268b085739d53af29eb14267ccd778891dec84ee3b2`.

## May reference comparison

| Pinned reference | Inspected source | October decision |
|---|---|---|
| Saai `fadb4f24e36d860a9ce4d5155bb30568df80ea4b` | `benchmarks/saai-winner/code/retrieval/kb_tool.py:124-133`, `code/retrieval/reader.py:56-90` | Literal grep is useful for identifiers. October uses typed exact keys and returns every posting with a case cutoff, without grep's 60-hit cap or substring/regex false matches. |
| Amogh `54f1b0c991e0e8091815c4169f22d31cda749d7a` | `benchmarks/amogh/code/classifier.py:166-195` | Deterministic extraction and explicit ambiguity handling transfer. Company keyword scoring cannot establish a customer identity; names and near matches are never linked. |

## Known limitations and recommendation

**FAIL for M2 closure** because M2-4 requires 100% dev-sample cited-pair
reachability. Achieving it for the seven unlinked/absent resources would require
a separately justified source relationship or a later state-reconstruction
method; inventing a user/resource mapping or using sample answers in production
would violate the contract. The identity graph and bounded retrieval remain
usable as a reviewed M2 candidate. Do not start M3 until this gap is resolved
or the acceptance criterion is revised with a documented evidence standard.
