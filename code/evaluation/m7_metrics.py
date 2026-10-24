"""Evaluation-only M7 metrics; this module reads sample gold. Production code never imports it.

Reports, per split (dev = first 22 sample cases, holdout = last 10, report-only, all 32):
status accuracy, step P/R/F1, per-field accuracy, sequence accuracy, citation
validity, and every missed or extra canonical step with its root cause from
the M7 diagnostics. Also runs the M7-1 serialization fixture and compares with
the provisional M6 synthesis.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import load_context, read_output, validate_rows
from evaluation.m6_metrics import combined_row
from evaluation.scorer import key, score_rows
from flow.main import run_all as m6_run
from synthesis.main import run
from synthesis.ordering import canonical, renumber

ROOT = Path(__file__).resolve().parents[2]


def serialization_fixture(gold):
    """M7-1: deserialize each sample's canonical keys, scramble, re-emit with M7 ordering."""
    identical = []
    for row in gold:
        steps = [dict(s) for s in reversed(row['steps_json'])]
        emitted = renumber(canonical(steps))
        identical.append(emitted == row['steps_json'])
    return {'identical': sum(identical), 'total': len(identical)}


def summary(scored):
    m = scored['metrics']
    out = {k: round(m[k]['value'], 4) for k in ('status_accuracy', 'step_precision', 'step_recall', 'step_f1',
                                               'sequence_accuracy', 'field_accuracy', 'case_exact_match',
                                               'normalised_kendall_tau')}
    out['status_correct'] = f"{m['status_accuracy']['numerator']}/{m['status_accuracy']['denominator']}"
    out['steps'] = f"matched {m['step_precision']['numerator']}, predicted {m['step_precision']['denominator']}, " \
                   f"gold {m['step_recall']['denominator']}"
    out['matched_field_accuracy'] = {f: round(v['value'], 4) for f, v in m['matched_field_accuracy'].items()}
    out['evidence_validity_rate'] = (f"{m['evidence_validity_rate']['numerator']}/"
                                     f"{m['evidence_validity_rate']['denominator']}")
    return out


def miss_reason(step, diag):
    """Root cause of a missed gold step, from M7 diagnostics only."""
    target = (step['system_id'], step['resource_id'])
    for u in diag.get('unresolved', ()):
        if (u['system_id'], u['resource_id']) == target:
            return 'unresolved: ' + u['reason']
    for i in diag.get('items', ()):
        if (i['system_id'], i['resource_id']) == target:
            return f'resource planned as {i["compliance"]} (different treatment or phase)'
    return 'resource not linked to the subject by participant evidence M1–M6 can read'


def categorize(reason):
    for needle, label in (('not linked', 'unretrieved or unattributed record'),
                          ('condition is UNKNOWN', 'M5 condition UNKNOWN'),
                          ('M4 state is unresolved', 'M4 UNKNOWN state'),
                          ('no policy category', 'missing policy mapping'),
                          ('citation rejected', 'unsupported citation'),
                          ('M6', 'M6 process UNKNOWN/CONFLICTING'),
                          ('different treatment', 'different treatment or phase')):
        if needle in reason: return label
    return 'other'


def evaluate(dataset: Path, cache: Path | None = None):
    rows, diagnostics, pipeline = run(dataset, sample=True, cache=cache)
    gold = read_output(dataset / 'sample_output.csv')
    gold_by = {r['case_id']: r for r in gold}
    requests, evidence = load_context(dataset, 'sample')
    strict = validate_rows(rows, requests, evidence)
    diagnostic = validate_rows(rows, requests, evidence, nonstandard_allow_unproven_incomplete=True)
    m6_cases = {c['case_id']: c for c in m6_run(dataset, sample=True, cache=cache)['cases']}
    ordered = sorted(gold_by)
    splits = {'dev': ordered[:22], 'holdout': ordered[22:], 'all': ordered}
    pred_by = {r['case_id']: r for r in rows}
    report = {'m7_1_serialization': serialization_fixture(gold), 
              # Only the strict result may be cited for submission validity.
              'validator_strict_errors': strict.errors,
              'validator_diagnostic_nonstandard_errors': diagnostic.errors,
              'future_only_checks': sum(len(d.get('future_only', ())) for d in diagnostics.values()),
              'splits': {}, 'misses': {}, 'extras': {}, 'status_mismatches': {}}
    for split, ids in splits.items():
        p, g = [pred_by[i] for i in ids], [gold_by[i] for i in ids]
        m6 = [combined_row(m6_cases[i])[0] for i in ids]
        report['splits'][split] = {'m7': summary(score_rows(p, g, evidence, requests)),
                                   'm6_provisional': summary(score_rows(m6, g, evidence, requests))}
    categories = Counter()
    for cid in ordered:
        pk = Counter(map(key, pred_by[cid]['steps_json']))
        gk = Counter(map(key, gold_by[cid]['steps_json']))
        missed = [s for s in gold_by[cid]['steps_json'] if key(s) not in pk]
        extra = [s for s in pred_by[cid]['steps_json'] if key(s) not in gk]
        if missed:
            report['misses'][cid] = []
            for s in missed:
                reason = miss_reason(s, diagnostics[cid])
                categories[('dev' if cid in splits['dev'] else 'holdout', categorize(reason))] += 1
                report['misses'][cid].append({'step': list(key(s)), 'reason': reason})
        if extra:
            report['extras'][cid] = [list(key(s)) for s in extra]
        if pred_by[cid]['deletion_status'] != gold_by[cid]['deletion_status']:
            report['status_mismatches'][cid] = {'expected': gold_by[cid]['deletion_status'],
                                                'actual': pred_by[cid]['deletion_status'],
                                                'basis': diagnostics[cid].get('status_basis')}
    report['miss_categories'] = {f'{s}:{c}': n for (s, c), n in sorted(categories.items())}
    log = pipeline.guard.log
    report['citation_guard'] = {'checked': len(log), 'accepted': sum(e['accepted'] for e in log),
                                'rejected': [e for e in log if not e['accepted']]}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, Path('/tmp/m4-ingest-cache')), indent=1, sort_keys=True))
