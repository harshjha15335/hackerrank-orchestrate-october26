"""CLI: python3 code/evaluation/main.py {validate,score} FILE [--mode sample|full]."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import ContractError, load_context, validate_file

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'score'])
    parser.add_argument('predictions', type=Path)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--mode', choices=['sample', 'full'], default='sample')
    args = parser.parse_args(argv)
    result = validate_file(args.predictions, args.dataset, args.mode)
    payload = {'validation': {'valid': result.valid, 'row_count': result.row_count, 'errors': result.errors}}
    if args.command == 'score':
        if args.mode != 'sample':
            parser.error('score supports only sample mode; full submission gold is unavailable')
        try:
            from evaluation.scorer import evaluate_sample
            requests, evidence = load_context(args.dataset, 'sample')
            payload['evaluation'] = evaluate_sample(args.predictions, args.dataset, evidence, requests)
        except (ContractError, OSError, ValueError, KeyError) as exc:
            payload['scoring_error'] = str(exc)
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    if not result.valid or 'scoring_error' in payload:
        return 1
    if args.command == 'score' and payload['evaluation']['all']['mismatches']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
