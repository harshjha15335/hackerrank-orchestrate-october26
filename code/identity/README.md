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
comes from source text; `correlated` requires a shared explicit trace ID
in the same file whose admissible lines name one resolved subject: with the
identity graph, every identifier in the trace (email, user ID, phone, hash)
must be the subject's at the cutoff and held by nobody else, ever (pre-M9
F-03: a subject's email and user ID together are one identity); without the
graph, two customer identifiers keep the trace ambiguous. `mixed_context`
marks a record with more than one direct email/user identity (M4 verifies it;
`owner_conflict` marks one the graph does not tie exclusively to the subject).
Screenshot rows that are not evidence at the cutoff, including screenshots
captured after it, are returned by `excluded_visual` for diagnostics only. All are candidates for later
verification, not proof of the resource's current state. Future captures are
excluded with an inclusive, timezone-aware case cutoff.

Historic values come from both old and new audit transition values at or
before the case cutoff. Current snapshot values are reversed through later
transitions when viewing an earlier case. Email matching is exact after
case-folding, phones use digits, and hashes are opaque exact strings.
Ambiguous matches return candidate user IDs and no chosen user.

SQL table scope is exposed separately by `identity.snapshots`; absent rows are
never customer-specific hits. The original dev-sample recall is 31/38: three
SQL negative scopes are discoverable separately, and four records/queries
remain unattributed. See the M2 checkpoint and forensic reports. The CLI does
not fabricate links to improve a public sample score.
