"""Inspect physical-copy states for one case or all requests; no final policy decision."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest.evidence import ingest, parse_time
from state.engine import reconstruct


def build(dataset: Path, cache: Path | None = None):
    graph = IdentityGraph(dataset)
    observations, coverage, discrepancies = ingest(dataset, cache)
    anomalies = {(d['file_id'], d['locator']) for d in discrepancies
                 if d['reason'] == 'record_time_after_manifest_capture'}
    return graph, EvidenceIndex(observations, anomalies, graph), SnapshotIndex(observations, coverage), discrepancies


def run_case(case, graph, evidence, scopes, dataset, anomalies):
    resolution = graph.resolve(case)
    hits = evidence.find(resolution)
    return reconstruct(resolution, hits, scopes, dataset, anomalies)


def run_all(dataset: Path, sample=False, cache: Path | None = None):
    graph, evidence, scopes, discrepancies = build(dataset, cache)
    anomalies = {(d['file_id'], d['locator']) for d in discrepancies
                 if d['reason'] == 'record_time_after_manifest_capture'}
    cases = [run_case(case, graph, evidence, scopes, dataset, anomalies)
             for case in graph.requests(sample)]
    latest = [a for case in cases for a in case['latest']]
    all_assertions = [a for case in cases for a in case['assertions']]
    drift = sorted({(c['case_id'], system, resource)
                    for c in cases
                    for system, resource in {(a['system_id'], a['resource_id']) for a in c['latest']}
                    if len({a['state'] for a in c['latest']
                            if a['system_id'] == system and a['resource_id'] == resource and a['supported']}) > 1})
    return {'case_count': len(cases), 'latest_state_counts': dict(sorted(Counter(a['state'] for a in latest).items())),
            'assertion_counts': dict(sorted(Counter(a['state'] for a in all_assertions).items())),
            'unresolved_states': sum(not a['supported'] for a in latest),
            'conflicting_latest_states': sum(bool(a['conflicts']) for a in latest),
            'replica_drift_count': len(drift), 'replica_drift': drift,
            'cutoff_violations': sum(parse_time(a['captured_at']) > parse_time(c['audit_at'])
                                     for c in cases for a in c['assertions']),
            'timestamp_anomalies': discrepancies, 'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', help='case ID for detailed inspection')
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[2] / 'dataset')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    args = parser.parse_args()
    result = run_all(args.dataset, args.sample, args.cache)
    if args.case:
        match = next((c for c in result['cases'] if c['case_id'] == args.case), None)
        if match is None: parser.error('case ID not found')
        result = match
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__': main()
