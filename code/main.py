"""M0 format-only stub. This deliberately performs no deletion auditing."""
import argparse
import csv
from pathlib import Path


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New destination outside dataset/; root output.csv is protected')
    args = parser.parse_args(argv)
    destination = args.output.resolve()
    if destination == root / 'output.csv' or destination.is_relative_to(root / 'dataset'):
        parser.error('M0 cannot write root output.csv or official dataset files')
    with (root / 'dataset/deletion_requests.csv').open(encoding='utf-8', newline='') as stream:
        ids = sorted(row['case_id'] for row in csv.DictReader(stream))
    # Exclusive creation also protects previous run artifacts and symlink targets.
    with destination.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['case_id', 'deletion_status', 'steps_json'])
        writer.writerows((case, 'NOT_APPLICABLE', '[]') for case in ids)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
