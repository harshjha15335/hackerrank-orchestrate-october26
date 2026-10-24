"""Inspect M5 policy decisions for one case or all requests; no output.csv is written."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intent.classifier import IntentClassifier
from ingest.evidence import ingest
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from state.engine import reconstruct
from policy.engine import Context, decide_case
from policy.unknowns import classify_unknowns

ROOT = Path(__file__).resolve().parents[2]


def run_all(dataset: Path, sample=False, cache: Path | None = None, rules: Path | None = None,
            category_map=None, bindings=None):
    dataset = Path(dataset)
    graph = IdentityGraph(dataset)
    observations, coverage, discrepancies = ingest(dataset, cache)
    evidence, scopes = EvidenceIndex(observations), SnapshotIndex(observations, coverage)
    anomalies = {(d['file_id'], d['locator']) for d in discrepancies
                 if d['reason'] == 'record_time_after_manifest_capture'}
    ctx = Context(observations, rules or dataset / 'deletion_rules.csv', category_map, bindings)
    classifier = IntentClassifier()
    cases, unknown_rows = [], []
    for request in graph.requests(sample):
        resolution = graph.resolve(request)
        state = reconstruct(resolution, evidence.find(resolution), scopes, dataset, anomalies)
        policy = decide_case(ctx, state, resolution)
        policy['intent'] = classifier.classify(request['request_text']).intent
        unknown_rows.extend(classify_unknowns(state, policy, ctx))
        cases.append(policy)
    decisions = [d for c in cases for d in c['decisions']]
    resources = [r for c in cases for r in c['resources']]
    return {
        'case_count': len(cases),
        'rules': [r.__dict__ for r in ctx.table.rules],
        'copy_compliance': dict(sorted(Counter(d['compliance'] for d in decisions).items())),
        'resource_compliance': dict(sorted(Counter(r['compliance'] for r in resources).items())),
        'category_status': dict(sorted(Counter(d['category_status'] for d in decisions).items())),
        'condition_outcomes': dict(sorted(Counter(f'{d["rule_id"]}:{d["condition_outcome"]}'
                                                  for d in decisions if d['rule_id']).items())),
        'retain_category_delete_steps': sum(
            1 for d in decisions if d['required_action'] == 'RETAIN'
            for phase, op, _ in d['obligations'] if op == 'DELETE_RECORD'),
        'unknown_root_causes': unknown_rows,
        'cases': cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', help='case ID for detailed inspection')
    parser.add_argument('--sample', action='store_true', help='use the 32 public sample requests')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--rules', type=Path, help='alternative deletion_rules.csv (default: dataset copy)')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    parser.add_argument('--summary', action='store_true', help='omit per-case detail')
    args = parser.parse_args()
    result = run_all(args.dataset, args.sample, args.cache, args.rules)
    if args.case:
        match = next((c for c in result['cases'] if c['case_id'] == args.case), None)
        if match is None: parser.error('case ID not found')
        result = match
    elif args.summary:
        result = {k: v for k, v in result.items() if k not in ('cases', 'unknown_root_causes')}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__':
    main()
