"""Inspect M6 data-flow and restore-path assessments; no output.csv is written."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flow.dependencies import build, index_activity, precedence
from flow.engine import FlowContext, assess_case
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest.evidence import ingest
from intent.classifier import IntentClassifier
from policy.engine import Context, decide_case
from state.engine import reconstruct

ROOT = Path(__file__).resolve().parents[2]


def backup_policy(assessment, policy):
    """The M5 rule that governs the archive record itself (restore access is separate)."""
    decisions = [d for d in policy['decisions']
                 if (d['system_id'], d['resource_id']) == (assessment.system_id, assessment.resource_id)]
    actions = sorted({d['required_action'] for d in decisions if d['required_action']})
    return {'m5_required_actions': actions, 'm5_compliance': sorted({d['compliance'] for d in decisions}),
            'delete_forbidden': 'RETAIN' in actions or not decisions}


def case_view(request, graph, evidence, scopes, ctx, fctx, indexes, dataset, anomalies, classifier):
    resolution = graph.resolve(request)
    state = reconstruct(resolution, evidence.find(resolution), scopes, dataset, anomalies)
    policy = decide_case(ctx, state, resolution)
    assessments = assess_case(fctx, resolution)
    edges = build(fctx, indexes, resolution, assessments, policy['resources'], policy['decisions'])
    m4_process = sorted({(a['system_id'], a['resource_id']) for a in state['latest']
                         if (a['resource_id'] or '').startswith(('data_flow_', 'backup_'))})
    found = {(a.system_id, a.resource_id) for a in assessments}
    return {'case_id': request['case_id'], 'user_id': resolution.user_id, 'audit_at': resolution.audit_at,
            'intent': classifier.classify(request['request_text']).intent,
            'flows': [a.as_dict() for a in assessments if a.kind == 'DATA_FLOW'],
            'restores': [dict(a.as_dict(), retention=backup_policy(a, policy))
                         for a in assessments if a.kind == 'RESTORE_PATH'],
            'dependencies': edges,
            'precedence': precedence(assessments, policy['resources'], edges),
            'm4_linked_not_attributed': [list(k) for k in m4_process if tuple(k) not in found],
            'policy': policy}


def run_all(dataset: Path, sample=False, cache: Path | None = None):
    dataset = Path(dataset)
    graph = IdentityGraph(dataset)
    observations, coverage, discrepancies = ingest(dataset, cache)
    anomalies = {(d['file_id'], d['locator']) for d in discrepancies
                 if d['reason'] == 'record_time_after_manifest_capture'}
    evidence, scopes = EvidenceIndex(observations, anomalies, graph), SnapshotIndex(observations, coverage)
    ctx = Context(observations, dataset / 'deletion_rules.csv', anomalies=anomalies)
    fctx = FlowContext(observations, anomalies)
    indexes = index_activity(fctx.activity)
    classifier = IntentClassifier()
    cases = [case_view(r, graph, evidence, scopes, ctx, fctx, indexes, dataset, anomalies, classifier)
             for r in graph.requests(sample)]
    flows = [f for c in cases for f in c['flows']]
    restores = [r for c in cases for r in c['restores']]
    return {'case_count': len(cases),
            'flow_status': dict(sorted(Counter(f['status'] for f in flows).items())),
            'restore_status': dict(sorted(Counter(r['status'] for r in restores).items())),
            'attribution': dict(sorted(Counter(f'{a["kind"]}:{a["attribution"] or "none"}'
                                               for a in flows + restores).items())),
            'deciding_class': dict(sorted(Counter(f'{a["kind"]}:{a["deciding"]["evidence_class"]}'
                                                  for a in flows + restores if a['deciding']).items())),
            'ownership_conflicts': sum(bool(a['ownership_conflicts']) for a in flows + restores),
            'later_unverified_claims': sum(bool(a['later_unverified_claims']) for a in flows + restores),
            'dependency_kinds': dict(sorted(Counter(e['kind'] for c in cases for e in c['dependencies']).items())),
            'm4_linked_not_attributed': sum(len(c['m4_linked_not_attributed']) for c in cases),
            'delete_steps_on_backups': sum(1 for c in cases for r in c['restores'] for o in r['obligations']
                                           if o['operation'] == 'DELETE_RECORD'),
            'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', help='case ID for detailed inspection')
    parser.add_argument('--sample', action='store_true', help='use the 32 public sample requests')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    parser.add_argument('--summary', action='store_true', help='omit per-case detail')
    parser.add_argument('--with-policy', action='store_true', help='keep the embedded M5 policy output')
    args = parser.parse_args()
    result = run_all(args.dataset, args.sample, args.cache)
    if not args.with_policy:
        for c in result['cases']: c.pop('policy')
    if args.case:
        match = next((c for c in result['cases'] if c['case_id'] == args.case), None)
        if match is None: parser.error('case ID not found')
        result = match
    elif args.summary:
        result = {k: v for k, v in result.items() if k != 'cases'}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__':
    main()
