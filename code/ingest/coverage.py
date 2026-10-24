"""Generate a compact, reproducible Markdown report for all manifest entries."""
from collections import Counter
from pathlib import Path

from evidence import canonical_bytes, ingest
import hashlib


def report(dataset):
    obs, coverage, differences = ingest(dataset)
    types = Counter(o.source_type for o in obs)
    sql_tables = Counter()
    sql_topologies = Counter(o.topology for o in obs if o.source_type == 'sql')
    for row in coverage:
        if row['format'] == '.sql': sql_tables.update(row['tables'])
    digest = hashlib.sha256(canonical_bytes(obs)).hexdigest()
    lines = ['# M1 evidence coverage', '',
             f'- Manifest entries: {len(coverage)}',
             f'- Parsed files: {sum(x["status"] == "parsed" for x in coverage)}',
             f'- Awaiting M8 multimodal extraction: {sum(x["status"] == "needs_multimodal" for x in coverage)}',
             f'- Observations including activity and audit: {len(obs)}',
             f'- Canonical JSONL SHA-256: `{digest}`',
             f'- Source-type counts: `{dict(sorted(types.items()))}`',
             f'- SQL table rows: `{dict(sorted(sql_tables.items()))}`',
             f'- SQL topology rows: `{dict(sorted(sql_topologies.items()))}`',
             f'- Timestamp discrepancies: {len(differences)}', '',
             '| File ID | Source path | Format | Status | Observations |',
             '|---|---|---|---|---:|']
    for item in coverage:
        lines.append(f'| {item["file_id"]} | `{item["source_path"]}` | {item["format"]} | {item["status"]} | {item["observations"]} |')
    lines += ['', '## Timestamp discrepancies', '']
    for item in differences: lines.append(f'- `{item["file_id"]}` `{item["locator"]}`: {item["reason"]}')
    if not differences: lines.append('- None')
    lines += ['', 'Regenerate from the repository root with '
               '`python3 code/ingest/coverage.py > /tmp/M1_COVERAGE.md`.',
              'The generated report contains no personal identifiers or raw evidence.', '']
    return '\n'.join(lines).rstrip()


if __name__ == '__main__':
    print(report(Path(__file__).resolve().parents[2] / 'dataset'))
