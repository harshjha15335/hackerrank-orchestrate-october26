"""Evaluation-only provisional M5 metrics; this module reads sample gold.

It turns M5 policy decisions into a *provisional* steps_json so that the
development split can be scored. It is not the M7 synthesiser: it has no flow
planning (M6), no dependency hook or citation guard (M7), and an UNRESOLVED
resource can never make a case COMPLETE.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import OPERATIONS, load_context, read_output
from evaluation.scorer import score_rows
from intent.classifier import DELETE
from policy.main import run_all

ROOT = Path(__file__).resolve().parents[2]
ORDER = {op: i for phase in OPERATIONS.values() for i, op in enumerate(phase)}
PHASES = {p: i for i, p in enumerate(OPERATIONS)}
FLOW_OPERATIONS = {'REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED'}


def provisional_row(case):
    if case['intent'] != DELETE:
        return {'case_id': case['case_id'], 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []}, 'not_applicable'
    resources = [r for r in case['resources'] if r['compliance'] != 'DEFERRED_M6']
    unresolved = any(r['compliance'] == 'UNRESOLVED' for r in resources) or not resources
    violation = any(r['compliance'] == 'VIOLATION' or r['restore_risk'] for r in resources)
    status = 'COMPLETE' if not (unresolved or violation) else 'INCOMPLETE'
    steps = []
    for r in resources:
        if r['compliance'] == 'UNRESOLVED': continue
        for phase, op, state in tuple(r['obligations']) + tuple(r['restore_obligations']):
            cited = phase == 'FINDING' or status == 'COMPLETE'
            steps.append({'phase': phase, 'operation': op, 'state': state, 'system_id': r['system_id'],
                          'resource_id': r['resource_id'],
                          'evidence_id': r['deciding_copy']['evidence_id'] if cited else ''})
    steps.sort(key=lambda s: (PHASES[s['phase']], ORDER[s['operation']], s['system_id'], s['resource_id']))
    for n, s in enumerate(steps, 1): s['step_no'] = n
    reason = 'unresolved' if unresolved and not violation else ('violation' if violation else 'compliant')
    return {'case_id': case['case_id'], 'deletion_status': status, 'steps_json': steps}, reason


def retention_counterfactual(case):
    """What-if only: security records with UNKNOWN retention treated as retained."""
    case = copy.deepcopy(case)
    for r in case['resources']:
        decisions = [d for d in case['decisions'] if (d['system_id'], d['resource_id']) ==
                     (r['system_id'], r['resource_id'])]
        if (r['compliance'] == 'UNRESOLVED' and decisions and
                all(d['required_action'] == 'RETAIN' and d['condition_outcome'] == 'UNKNOWN' and
                    d['observed_state'] in ('PRESENT', 'REDACTED') for d in decisions)):
            r['compliance'] = 'COMPLIANT'
            r['obligations'] = [('VERIFICATION', 'VERIFY_RECORD_PRESENT', 'PRESENT')]
    return case


def without_flows(rows):
    out = []
    for row in rows:
        steps = [dict(s) for s in row['steps_json'] if s['operation'] not in FLOW_OPERATIONS]
        for n, s in enumerate(steps, 1): s['step_no'] = n
        out.append(dict(row, steps_json=steps))
    return out


def summary(scored):
    m = scored['metrics']
    return {k: round(m[k]['value'], 4) for k in ('status_accuracy', 'step_precision', 'step_recall', 'step_f1',
                                                   'sequence_accuracy', 'field_accuracy')} | {
        'status_correct': f"{m['status_accuracy']['numerator']}/{m['status_accuracy']['denominator']}",
        'evidence_id_matched': round(m['matched_field_accuracy']['evidence_id']['value'], 4)}


def evaluate(dataset: Path, cache: Path | None = None):
    result = run_all(dataset, sample=True, cache=cache)
    gold = {r['case_id']: r for r in read_output(dataset / 'sample_output.csv')}
    requests, evidence = load_context(dataset, 'sample')
    ordered = sorted(gold)
    splits = {'dev': ordered[:22], 'holdout': ordered[22:]}
    report = {}
    for label, transform in (('strict', lambda c: c), ('retention_counterfactual', retention_counterfactual)):
        rows, reasons = {}, {}
        for case in result['cases']:
            rows[case['case_id']], reasons[case['case_id']] = provisional_row(transform(case))
        section = {}
        for split, ids in splits.items():
            p, g = [rows[i] for i in ids], [gold[i] for i in ids]
            section[split] = {'all_steps': summary(score_rows(p, g, evidence, requests)),
                              'policy_scope_steps': summary(score_rows(without_flows(p), without_flows(g),
                                                                       evidence, requests)),
                              'status_basis': {i: reasons[i] for i in ids}}
        report[label] = section
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, Path('/tmp/m4-ingest-cache')), indent=1, sort_keys=True))
