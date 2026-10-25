# Ghost Data Still Exists: deletion-audit agent

This is a deterministic, evidence-first deletion auditor. For each request in `dataset/deletion_requests.csv` it:

1. decides whether the person asked for deletion;
2. reconstructs the subject's current and historical identifiers;
3. links evidence to the subject only when the evidence itself names the subject and no one else;
4. rebuilds the state of every copy at `audit_at`;
5. applies `deletion_rules.csv`;
6. plans remediation that is ordered, with data flows and restores handled first;
7. cites only evidence that a citation guard re-proves.

When something cannot be proven, it stays unresolved. The agent does not guess.

## Requirements

- Python 3.11 or newer. Only the standard library is used at runtime, including `sqlite3`.
- `pdftotext` from poppler-utils, for PDF evidence. Install it with `apt-get install poppler-utils` or `brew install poppler`. If it is missing, the run stops with an error instead of skipping PDFs.
- No API keys, network access or model provider.
- Tests only: `pip install -r code/evaluation/requirements-test.txt` (pytest).

## Run

From the repository root, with the official `dataset/` folder in place:

```sh
python3 code/main.py                     # writes ./output.csv (518 rows)
python3 code/main.py --output /tmp/x.csv # or any path outside dataset/
```

A run takes about 30 seconds and is byte-for-byte deterministic. It reads only participant-facing files under `dataset/`, never `sample_output.csv`, and it never writes inside `dataset/`.

Other commands:

```sh
python3 code/synthesis/main.py --sample --case <case_id> --explain   # inspect one sample case
python3 code/evaluation/main.py validate output.csv --mode full     # strict contract validator
python3 code/evaluation/pre_m9_metrics.py > metrics.json            # sample scores, 518 checks, safety probes
python3 -m pytest -q code                                           # test suite
```

## Architecture

| Stage | Package | Role |
|---|---|---|
| M1 | `ingest/` | Parses SQL snapshots, JSON, logs, text and PDF text into observations with capture times. Quarantines timestamp anomalies. |
| M2 | `identity/` | Builds an identity graph from snapshot and audit history. Retrieval uses exact identifiers. Trace joins require exclusive ownership. Owner conflicts block attribution. |
| M3 | `intent/` | Offline multilingual rules decide whether the request authorizes deletion. Requests that don't are NOT_APPLICABLE with `[]`. |
| M4 | `state/` | Reconstructs per-copy state at `audit_at`. Workflow results are claims; only records prove state. Mixed or foreign identity gives UNKNOWN. |
| M5 | `policy/` | Maps categories and conditions to `deletion_rules.csv` treatments: DELETE, REDACT, ANONYMIZE, RETAIN or TOMBSTONE. Anonymization needs corroborated evidence; nested linkage keys block it. |
| M6 | `flow/` | Finds sync, import, export, backup and restore paths that can recreate data. Builds the dependency order. |
| M7 | `synthesis/` | Produces findings, remediation and verification in contract order, through the citation guard. |
| M8 | `vision/` | Screenshot facts from committed manual fixtures (`vision/prompt.md` is the schema). No runtime model. |

Each package has its own README with details.

## Evaluation

See `evaluation/evaluation_report.md` and `evaluation/usage_report.md`:

- dev status accuracy is 19/22 and step F1 is 0.780;
- runtime usage is 0 model calls, 0 tokens and $0;
- the repository's strict contract validator still rejects 77 of 518 rows (114 errors) where the required evidence is not in the dataset. The reports list each of those rows.
