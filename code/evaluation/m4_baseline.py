"""Evaluation-only provisional M4 status baseline; this module reads sample gold."""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import read_output
from intent.classifier import IntentClassifier, DELETE
from state.main import run_all


def baseline(dataset: Path, cache: Path | None = None):
    states = run_all(dataset, sample=True, cache=cache)['cases']
    with (dataset / 'sample_deletion_requests.csv').open(newline='', encoding='utf-8') as f:
        requests = list(csv.DictReader(f))
    gold = {r['case_id']: r['deletion_status'] for r in read_output(dataset / 'sample_output.csv')}
    outcomes = []
    for i, (request, case) in enumerate(zip(requests, states)):
        assert request['case_id'] == case['case_id']
        intent = IntentClassifier().classify(request['request_text']).intent
        if intent != DELETE: status = 'NOT_APPLICABLE'
        else:
            # Deliberate M5 DELETE-all stub: any observed physical copy means
            # incomplete, without policy exemptions or remediation steps.
            status = ('INCOMPLETE' if any(a['supported'] and a['state'] not in ('ABSENT', 'DISABLED', 'RESTORE_BLOCKED')
                                          for a in case['latest']) else 'COMPLETE')
        outcomes.append({'case_id': case['case_id'], 'split': 'dev' if i < 22 else 'holdout',
                         'predicted': status, 'gold': gold[case['case_id']]})
    dev = [r for r in outcomes if r['split'] == 'dev']
    return {'dev_status_accuracy': {'correct': sum(r['predicted'] == r['gold'] for r in dev),
                                    'total': len(dev)}, 'cases': outcomes}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[2] / 'dataset')
    args = parser.parse_args()
    print(json.dumps(baseline(args.dataset, Path('/tmp/m4-ingest-cache')), sort_keys=True))
