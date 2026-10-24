"""CLI to inspect M1 observations and manifest coverage."""
import argparse
import hashlib
import json
from pathlib import Path

from evidence import canonical_bytes, ingest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[2] / 'dataset')
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path, help='New JSONL destination; dataset paths are forbidden')
    args = parser.parse_args()
    observations, coverage, discrepancies = ingest(args.dataset, args.cache)
    data = canonical_bytes(observations)
    if args.output:
        target = args.output.resolve()
        if target.is_relative_to(args.dataset.resolve()): parser.error('cannot write inside dataset')
        with target.open('xb') as stream: stream.write(data)
    print(json.dumps({'manifest_files': len(coverage), 'observations': len(observations),
                      'sha256': hashlib.sha256(data).hexdigest(), 'coverage': coverage,
                      'time_discrepancies': discrepancies}, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__': main()
