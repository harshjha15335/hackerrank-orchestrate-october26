# M2 identity inspection

From the repository root, with Python 3.11+ and `pdftotext`:

```sh
python3 code/identity/main.py --case case_33 > /tmp/m2-case.json
python3 code/identity/main.py --sample --case case_01 > /tmp/m2-sample.json
python3 -m pytest -q -p no:cacheprovider code/evaluation/tests code/ingest/tests code/identity/tests
```

The CLI emits an identity resolution and all time-eligible evidence references
with their file/activity/audit ID, source path, locator, system, resource,
capture timestamp and match strength. It does not decide resource state or
deletion status. `direct` comes from explicit identifier fields; `context`
comes from source text; `correlated` comes from a trace, export row or PDF
document containing a direct match elsewhere; `mixed_context` marks a record
with more than one direct email/user identity. All are candidates for later
verification, not proof of the resource's current state. Future captures are
excluded with an inclusive, timezone-aware case cutoff.

Historic values come from both old and new audit transition values at or
before the case cutoff. Current snapshot values are reversed through later
transitions when viewing an earlier case. Email matching is exact after
case-folding, phones use digits, and hashes are opaque exact strings.
Ambiguous matches return candidate user IDs and no chosen user.

The M2 dev-sample recall gate remains unmet for seven cited pairs whose cited
resource records have no identity link, including absent resources that never
appear in participant evidence. See the M2 checkpoint report. The CLI does
not fabricate those links to improve a public sample score.
