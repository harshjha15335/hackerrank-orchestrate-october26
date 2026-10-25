"""M8 screenshot extraction summary.

    python3 code/vision/main.py                                  # counters, records, anomalies (JSON)
    python3 code/vision/main.py --cache /tmp/m8-vision-cache --ledger /tmp/m8/ledger.jsonl

Every extraction in M8 comes from a committed manual fixture; the ledger shows
model_call=false and no token counts for each of them. Nothing is written
inside dataset/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.adapter import load

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--cache', type=Path, help='content-addressed extraction cache directory')
    parser.add_argument('--ledger', type=Path, help='write the provider-call ledger as JSON lines (new file)')
    args = parser.parse_args(argv)
    for path in (args.cache, args.ledger):
        if path and path.resolve().is_relative_to((ROOT / 'dataset').resolve()):
            parser.error('M8 never writes inside dataset/')
    evidence = load(args.dataset, args.cache)
    if args.ledger:
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        with args.ledger.open('x', encoding='utf-8') as stream:
            for row in evidence.ledger: stream.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps({'counters': evidence.counters,
                      'methods': sorted({e.document['provenance']['method'] for e in evidence.extractions if e.document}),
                      'observations': len(evidence.observations), 'records': evidence.records,
                      'discrepancies': evidence.discrepancies, 'unresolved_times': evidence.unresolved_times},
                     indent=1, sort_keys=True))
    return 0 if all(e.document is not None for e in evidence.extractions) else 1


if __name__ == '__main__':
    raise SystemExit(main())
