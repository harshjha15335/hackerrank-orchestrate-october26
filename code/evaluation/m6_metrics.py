"""Evaluation-only M6 metrics; this module reads sample gold.

1. Flow/restore step precision and recall per split, with every missed or
   extra expected obligation explained from the M6 assessment.
2. A *provisional* combined steps_json (M5 policy obligations plus M6
   flow/restore obligations) scored before and after M6. It is not the M7
   synthesiser: no citation guard, no dependency reordering (operation-table
   order only), and any UNRESOLVED resource or UNKNOWN/CONFLICTING process
   keeps a case from being COMPLETE.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import OPERATIONS, load_context, read_output
from evaluation.m5_metrics import provisional_row as m5_row, summary
from evaluation.scorer import key, score_rows
from flow.main import run_all
from intent.classifier import DELETE

ROOT = Path(__file__).resolve().parents[2]
ORDER = {op: i for phase in OPERATIONS.values() for i, op in enumerate(phase)}
PHASES = {p: i for i, p in enumerate(OPERATIONS)}
PROCESS_OPS = {'REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED',
               'REPORT_RESTORE_RISK', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED'}
RISK = {'ACTIVE', 'RESTORE_ENABLED'}


def combined_row(case):
    """M5 record obligations + M6 process obligations, operation-table order."""
    if case['intent'] != DELETE:
        return {'case_id': case['case_id'], 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []}, 'not_applicable'
    process = {(a['system_id'], a['resource_id']): a for a in case['flows'] + case['restores']}
    records = []
    for r in case['policy']['resources']:
        key_ = (r['system_id'], r['resource_id'])
        if r['compliance'] == 'DEFERRED_M6': continue
        if key_ in process:
            # The archive record is retained under M5; restore access is M6's.
            m6 = process[key_]
            reasons = {d['reason'] for d in case['policy']['decisions']
                       if (d['system_id'], d['resource_id']) == key_}
            if r['compliance'] == 'UNRESOLVED' and not (m6['supported'] and reasons <= {'M4 state is unresolved'}):
                records.append(dict(r, restore_obligations=())); continue
            if r['compliance'] == 'VIOLATION':
                records.append(dict(r, restore_obligations=())); continue
            continue
        records.append(dict(r, restore_obligations=()))
    unresolved = (any(r['compliance'] == 'UNRESOLVED' for r in records) or
                  any(not a['supported'] for a in process.values()) or not (records or process))
    violation = (any(r['compliance'] == 'VIOLATION' for r in records) or
                 any(a['status'] in RISK for a in process.values()))
    status = 'COMPLETE' if not (unresolved or violation) else 'INCOMPLETE'
    steps = []
    for r in records:
        if r['compliance'] == 'UNRESOLVED': continue
        for phase, op, state in r['obligations']:
            cited = phase == 'FINDING' or status == 'COMPLETE'
            steps.append({'phase': phase, 'operation': op, 'state': state, 'system_id': r['system_id'],
                          'resource_id': r['resource_id'],
                          'evidence_id': r['deciding_copy']['evidence_id'] if cited else ''})
    for a in process.values():
        for o in a['obligations']:
            cited = o['phase'] == 'FINDING' or status == 'COMPLETE'
            steps.append({'phase': o['phase'], 'operation': o['operation'], 'state': o['state'],
                          'system_id': a['system_id'], 'resource_id': a['resource_id'],
                          'evidence_id': a['deciding']['evidence_id'] if cited else ''})
    steps.sort(key=lambda s: (PHASES[s['phase']], ORDER[s['operation']], s['system_id'], s['resource_id']))
    for n, s in enumerate(steps, 1): s['step_no'] = n
    reason = 'unresolved' if unresolved and not violation else ('violation' if violation else 'compliant')
    return {'case_id': case['case_id'], 'deletion_status': status, 'steps_json': steps}, reason


def m5_only(case):
    return m5_row(dict(case['policy'], intent=case['intent']))


def _explain(case, step):
    found = next((a for a in case['flows'] + case['restores']
                  if (a['system_id'], a['resource_id']) == (step['system_id'], step['resource_id'])), None)
    if found is None:
        return 'no subject-attributed admissible evidence names this process'
    return f'M6 status {found["status"]}: {found["reason"]}'


def process_scores(cases, gold, ids):
    tp = fp = fn = ev_ok = ev_total = 0
    missed, extra = [], []
    for cid in ids:
        case = cases[cid]
        predicted = [s for s in combined_row(case)[0]['steps_json'] if s['operation'] in PROCESS_OPS]
        expected = [s for s in gold[cid]['steps_json'] if s['operation'] in PROCESS_OPS]
        pk, gk = Counter(map(key, predicted)), Counter(map(key, expected))
        hit = pk & gk
        tp += sum(hit.values()); fp += sum((pk - gk).values()); fn += sum((gk - pk).values())
        for s in expected:
            if key(s) not in pk:
                missed.append({'case_id': cid, 'step': list(key(s)), 'root_cause': _explain(case, s)})
            else:
                p = next(x for x in predicted if key(x) == key(s))
                ev_total += 1; ev_ok += p['evidence_id'] == s['evidence_id']
        for s in predicted:
            if key(s) not in gk:
                extra.append({'case_id': cid, 'step': list(key(s)), 'basis': _explain(case, s)})
    return {'expected': tp + fn, 'predicted': tp + fp, 'matched': tp,
            'precision': tp / (tp + fp) if tp + fp else 1.0, 'recall': tp / (tp + fn) if tp + fn else 1.0,
            'evidence_id_match': f'{ev_ok}/{ev_total}', 'missed': missed, 'extra': extra}


def evaluate(dataset: Path, cache: Path | None = None):
    result = run_all(dataset, sample=True, cache=cache)
    cases = {c['case_id']: c for c in result['cases']}
    gold = {r['case_id']: r for r in read_output(dataset / 'sample_output.csv')}
    requests, evidence = load_context(dataset, 'sample')
    ordered = sorted(gold)
    splits = {'dev': ordered[:22], 'holdout': ordered[22:]}
    report = {'process_steps': {}, 'provisional_steps': {}, 'status_basis': {}}
    for split, ids in splits.items():
        report['process_steps'][split] = process_scores(cases, gold, ids)
        g = [gold[i] for i in ids]
        before = [m5_only(cases[i])[0] for i in ids]
        after_rows = [combined_row(cases[i]) for i in ids]
        report['provisional_steps'][split] = {
            'before_m6': summary(score_rows(before, g, evidence, requests)),
            'after_m6': summary(score_rows([r for r, _ in after_rows], g, evidence, requests))}
        report['status_basis'][split] = {i: basis for i, (_, basis) in zip(ids, after_rows)}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, Path('/tmp/m4-ingest-cache')), indent=1, sort_keys=True))
