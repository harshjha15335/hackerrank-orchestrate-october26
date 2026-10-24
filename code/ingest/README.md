# M1 evidence ingestion

Python 3.11+ and `pdftotext` are required; runtime uses the standard library.
From the repository root:

```sh
python3 code/ingest/main.py --output /tmp/m1-observations.jsonl > /tmp/m1-run.json
python3 code/ingest/coverage.py > /tmp/M1_COVERAGE.md
python3 -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests
```

Use a new output path for every run. `--cache /tmp/m1-cache` optionally caches
per-file extraction. Cache keys include source bytes, manifest metadata, parser
source hash and parser version. Cached results retain the same typed identifiers
as cold results. No cache is required for correctness. Neither command writes
inside `dataset/`; the CLI rejects dataset output paths and exclusive creation
prevents overwriting an existing output file. The coverage command prints a
summary and one row for each of the 94 manifest entries.

`Observation` contains file/activity/audit ID, source path and origin, precise
locator, manifest capture time, optional internal record/event times, system,
resource, category, state, original identifier and normalised lookup pairs,
all raw fields, source type and database topology. Unknown fields are `None`.
No observations are combined by resource ID. SQL table rows are read in rowid
order after loading each script into an in-memory SQLite database. `ATTACH`,
`DETACH` and virtual-table creation are denied. JSON snapshot and service export
records are traversed in source order. Logs and text keep each nonempty line
verbatim as well as parsed key/value or pipe fields. Text PDFs use `pdftotext
-layout`; images are marked `needs_multimodal` for M8.

Manifest `captured_at` is the capture timestamp. Record/event times describe
source contents and do not replace it. The coverage report lists detected
disagreements. Later case-specific queries must exclude observations whose
capture is after the case's `audit_at`; M1 intentionally retains them all.
Raw evidence text is stored as data and never executed as instructions.
