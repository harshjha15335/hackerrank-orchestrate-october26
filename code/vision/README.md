# M8 screenshot evidence

The 11 PNG screenshots in `dataset/evidence/images/` were marked
`needs_multimodal` by M1. M8 turns each one into a validated extraction and
then into M1 `Observation` rows (`source_type='image'`) that pass through the
same M2 identity index, M4 state rules, M5 policy, M6 flow engine and M7
citation guard as every other piece of evidence. Every PDF already had a text
layer, so M8 has no scanned-PDF work.

```sh
python3 code/vision/main.py                                      # extraction summary (JSON)
python3 code/vision/main.py --cache /tmp/m8-vision --ledger /tmp/m8/ledger.jsonl
python3 code/synthesis/main.py --output /tmp/m8/out.csv           # pipeline with screenshots
python3 code/synthesis/main.py --no-visual --output /tmp/m8/base.csv   # M7 ablation baseline
python3 code/evaluation/m8_metrics.py > /tmp/m8/metrics.json      # evaluation-only ablation
python3 -m pytest -q -p no:cacheprovider code/vision
```

## Where the extractions come from

**All 11 extractions are manual fixtures** (`fixtures/*.json`). They were
transcribed by the Claude Code agent session that built M8, by viewing each
PNG directly. No vision API was called: this environment has no API key for
one, so the usage ledger records `model_call=false` and no token counts for
every extraction. Each fixture states this in its `provenance` block and is
bound to the SHA-256 of the image bytes it was made from; a changed image
invalidates its fixture. The fixture provider's cache key also covers the
fixture files' content, so a corrected fixture is never shadowed by a cached
older transcription.

A model provider can be added as a `ModelProvider` subclass returning the
provider-reported token usage. The schema, retry and cache paths for that
case are tested with an offline fake (`tests/test_vision.py`), and no live
model provider ships with M8.

## Files

- `schema.py`: the strict structured-output schema. Unknown or missing keys,
  a wrong image hash, a provenance that contradicts itself, a malformed
  resource ID or a duplicate field are rejected.
- `prompt.md`: the extraction instructions a model provider would use. Its
  hash is part of the cache key.
- `extract.py`: providers, validate-and-retry-once, and the cache keyed by
  `sha256(image bytes) + prompt version + provider:model`. A damaged cache
  entry is ignored.
- `times.py`: turns visible times into UTC only when the screen states the
  date, time and zone. A missing year comes from the screen's one stated year,
  and a missing zone only from a column label such as "Time (UTC)".
- `adapter.py`: maps validated records to observations.

## Rules the adapter and later stages apply

- Only a `customer_record` or `process_record` with a **visible** resource ID
  becomes an observation. A resource ID is never derived from a file name,
  a catalog entry or a page title. Object-storage rows, the deleted-account
  reference page and cross-references emit nothing.
- An observation's raw fields are that record's own visible fields. Query
  history, timelines and other rows on the same screen never lend it an
  identity.
- The owning system comes from M5's resource-prefix map, or from the manifest
  origin when that origin is a known system. If the two disagree, nothing is
  emitted.
- Each visible time has a role: `record` (the record's own past event),
  `expiry` (a scheduled end), `generated` (when the shown result set was
  produced, such as a query execution; it must name its result set and the
  visible text that ties it to that set) or `page` (other screen metadata).
- If a record's own stated time is after the manifest capture, M1's
  `record_time_after_manifest_capture` anomaly is raised and the record is
  quarantined.
- Rows rendered together share a `result_set`. If the set's generation time,
  or any member row's own time, is after the manifest capture, every emitted
  record in the set gets `result_set_rendered_after_manifest_capture` and is
  quarantined: the screen shows the set as it was after the capture, not at
  it. The observation's `event_time` is that later instant, so the M2/M4/M6
  admissibility gates and the M7 citation guard reject it even without the
  anomaly list. The manifest capture time is never changed.
- Expiry times and unrelated page times never quarantine; a page time after
  capture is reported as `screen_time_after_manifest_capture`. Times without
  a stated date, year or zone stay unresolved and decide nothing.
- M4 (`state/engine.py`): a screenshot can show `PRESENT` but never `ABSENT`,
  `REDACTED` or `ANONYMIZED`. Account, support and analytics records need
  visible identifiers to count as `PRESENT`. A visible expiry at or before
  `audit_at` makes the state `UNKNOWN`, because an expiry is a schedule and
  not proof of deletion.
- M6 (`flow/evidence.py`): a connector screen that shows a continuous mode,
  a running status and a non-zero throughput together is a risk-only `ACTIVE`
  reading of class `visual`. Any one of them alone is `UNKNOWN`.
  A screenshot never shows a flow as disabled or a restore as blocked.
- Retention periods, restore controls and resource IDs that are not on the
  screen are listed under `not_visible` and are never filled in.
