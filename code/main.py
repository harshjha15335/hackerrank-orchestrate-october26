"""Ghost Data Still Exists: deletion-audit pipeline entry point.

    python3 code/main.py                      # writes <repo>/output.csv (518 rows)
    python3 code/main.py --output out.csv     # writes another path instead

Runs the audited production pipeline (M1 ingest -> M2 identity -> M3 intent ->
M4 state -> M5 policy -> M6 flows -> M7 synthesis and citation guard, with the
committed M8 screenshot fixtures) on dataset/deletion_requests.csv. It reads
only participant-facing files under dataset/ and never the public sample
answers. It makes no network or model calls.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthesis.main import run, serialize

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--output', type=Path, default=ROOT / 'output.csv',
                        help='destination CSV (default: output.csv at the repository root)')
    parser.add_argument('--cache', type=Path,
                        help='optional M1 extraction cache directory (default: a fresh temporary one)')
    args = parser.parse_args(argv)
    destination = args.output.resolve()
    if destination.is_relative_to(args.dataset.resolve()) or destination.is_relative_to((ROOT / 'dataset').resolve()):
        parser.error('refusing to write inside dataset/; the supplied dataset is read-only')
    with tempfile.TemporaryDirectory(prefix='ghost-data-cache-') as scratch:
        cache = args.cache or Path(scratch)
        cache.mkdir(parents=True, exist_ok=True)
        rows, _, _ = run(args.dataset, sample=False, cache=cache)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialize(rows), encoding='utf-8')
    print(f'wrote {len(rows)} rows to {destination}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
