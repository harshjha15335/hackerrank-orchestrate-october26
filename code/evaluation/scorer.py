"""Exact October metrics. This evaluation module alone loads sample gold."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from itertools import zip_longest
from pathlib import Path

from .contract import FIELDS, ContractError, read_output, step_shape


def key(step):
    return tuple(step[f] for f in ('phase', 'operation', 'system_id', 'resource_id'))


def metric(numerator, denominator, empty=1.0):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else empty}


def index_rows(rows):
    result = {}
    for row in rows:
        if row['case_id'] in result:
            raise ContractError(f'duplicate case_id: {row["case_id"]}')
        if not isinstance(row['steps_json'], list) or not all(step_shape(s) for s in row['steps_json']):
            raise ContractError(f'{row["case_id"]}: scorer requires arrays of seven typed step fields')
        result[row['case_id']] = row
    return result


def score_rows(predictions, gold, evidence=None, requests=None):
    """Score parsed rows, including invalid semantic values/order for sensitivity analysis.

    Cases align by exact ID; step-set metrics use multiset intersection; matched
    field metrics pair equal canonical keys FIFO (duplicate occurrences retained).
    Positional metrics use max(predicted, gold) slots per case, penalizing extras.
    """
    pred, expected = index_rows(predictions), index_rows(gold)
    cases = sorted(set(pred) | set(expected))
    counts = Counter()
    fields = Counter()
    mismatches = []
    for case in cases:
        p, g = pred.get(case), expected.get(case)
        ps, gs = (p['steps_json'] if p else []), (g['steps_json'] if g else [])
        pk, gk = list(map(key, ps)), list(map(key, gs))
        present = p is not None and g is not None
        counts['status'] += bool(present and p['deletion_status'] == g['deletion_status'])
        counts['case'] += bool(present and p == g)
        counts['step_count'] += bool(present and len(ps) == len(gs))
        counts['sequence'] += bool(present and pk == gk)
        counts['predicted'] += len(ps)
        counts['gold'] += len(gs)
        counts['matched'] += sum((Counter(pk) & Counter(gk)).values())
        counts['slots'] += max(len(ps), len(gs))
        differences = []
        if not present:
            differences.append({'kind': 'unexpected_case' if g is None else 'missing_case'})
        elif p['deletion_status'] != g['deletion_status']:
            differences.append({'kind': 'deletion_status', 'expected': g['deletion_status'], 'actual': p['deletion_status']})
        for position, (a, b) in enumerate(zip_longest(ps, gs), 1):
            for f in ('operation', 'system_id', 'resource_id', 'evidence_id'):
                counts[f] += bool(a is not None and b is not None and a[f] == b[f])
            if a != b:
                differences.append({'kind': 'step', 'position': position, 'expected': b, 'actual': a})
        if differences:
            mismatches.append({'case_id': case, 'differences': differences})
        positions = defaultdict(deque)
        for j, step in enumerate(gs):
            positions[key(step)].append(j)
        matched_positions = []
        for step in ps:
            if positions[key(step)]:
                j = positions[key(step)].popleft()
                matched_positions.append(j)
                for f in FIELDS:
                    fields[f] += step[f] == gs[j][f]
        # Normalised Kendall agreement (tau+1)/2, pooled across within-case pairs.
        for i, a in enumerate(matched_positions):
            for b in matched_positions[i + 1:]:
                counts['pairs'] += 1
                counts['concordant'] += a < b
        if evidence is not None and requests is not None:
            for step in ps:
                citation = step['evidence_id']
                if citation:
                    counts['citations'] += 1
                    counts['valid_citations'] += bool(citation in evidence and case in requests
                                                      and evidence[citation] <= requests[case])
    precision = metric(counts['matched'], counts['predicted'], empty=float(not counts['gold']))
    recall = metric(counts['matched'], counts['gold'], empty=float(not counts['predicted']))
    metrics = {
        'status_accuracy': metric(counts['status'], len(cases)),
        'case_exact_match': metric(counts['case'], len(cases)),
        'step_count_accuracy': metric(counts['step_count'], len(cases)),
        'step_precision': precision, 'step_recall': recall,
        'step_f1': metric(2 * counts['matched'], counts['predicted'] + counts['gold']),
        'sequence_accuracy': metric(counts['sequence'], len(cases)),
        'normalised_kendall_tau': metric(counts['concordant'], counts['pairs']),
        'field_accuracy': metric(sum(fields.values()), len(FIELDS) * counts['matched'],
                                 empty=float(not (counts['gold'] or counts['predicted']))),
    }
    for f in ('operation', 'system_id', 'resource_id', 'evidence_id'):
        metrics[f + '_accuracy'] = metric(counts[f], counts['slots'])
    metrics['matched_field_accuracy'] = {
        f: metric(fields[f], counts['matched'], empty=float(not (counts['gold'] or counts['predicted'])))
        for f in FIELDS}
    if evidence is not None and requests is not None:
        metrics['evidence_validity_rate'] = metric(counts['valid_citations'], counts['citations'])
    return {'case_count': len(cases), 'metrics': metrics, 'mismatches': mismatches}


def evaluate_sample(path: Path, dataset: Path, evidence: dict, requests: dict):
    gold = read_output(dataset / 'sample_output.csv')
    predictions = read_output(path)
    # Fixed checkpoint split by sample request order; no answer values influence it.
    ordered_ids = sorted(requests)
    splits = {'all': set(ordered_ids), 'dev': set(ordered_ids[:22]), 'holdout': set(ordered_ids[22:])}
    report = {}
    for name, ids in splits.items():
        selected = predictions if name == 'all' else [r for r in predictions if r['case_id'] in ids]
        report[name] = score_rows(selected, [r for r in gold if r['case_id'] in ids], evidence, requests)
    return report
