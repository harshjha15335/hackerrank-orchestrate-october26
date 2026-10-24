"""Evaluation-only M8 ablation; this module reads sample gold. Production code never imports it.

    python3 code/evaluation/m8_metrics.py > /tmp/m8/metrics.json

Runs the full pipeline with and without M8 screenshot observations and reports:
sample metrics per split (dev = first 22, holdout = last 10, report-only and not
blind), every changed 518 row, strict and nonstandard validator results, the
reassessment of the INCOMPLETE-without-finding rows and of the unknown
conditional-treatment items, citations that use a screenshot, extraction
counters (cold and warm cache) and the model-call ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import load_context, read_output, validate_rows
from evaluation.m7_metrics import summary
from evaluation.scorer import score_rows
from synthesis.main import run, serialize
from synthesis.reports import analyse, reason_class
from vision.adapter import load as load_visual

ROOT = Path(__file__).resolve().parents[2]
UNKNOWN_TREATMENT = 'unknown conditional treatment'


def sample_splits(dataset, cache):
    gold = {r['case_id']: r for r in read_output(dataset / 'sample_output.csv')}
    requests, evidence = load_context(dataset, 'sample')
    ordered = sorted(gold)
    splits = {'dev': ordered[:22], 'holdout': ordered[22:], 'all': ordered}
    out, rows_by = {}, {}
    for label, visual in (('without_visual', False), ('with_visual', True)):
        rows, _, _ = run(dataset, sample=True, cache=cache, visual=visual)
        rows_by[label] = {r['case_id']: r for r in rows}
        out[label] = {split: summary(score_rows([rows_by[label][i] for i in ids], [gold[i] for i in ids],
                                                evidence, requests)) for split, ids in splits.items()}
    out['changed_sample_rows'] = sorted(c for c in gold if rows_by['without_visual'][c] != rows_by['with_visual'][c])
    return out


def unknown_items(rows, diagnostics, only_no_finding=True):
    """(case, system, resource) items whose treatment is undecided: within the
    INCOMPLETE-without-finding rows (the M7 count), or within every case."""
    cases = ([c['case_id'] for c in analyse(rows, diagnostics)] if only_no_finding else sorted(diagnostics))
    items = set()
    for case in cases:
        for u in diagnostics[case].get('unresolved', ()):
            if reason_class(u['reason']) == UNKNOWN_TREATMENT:
                items.add((case, u['system_id'], u['resource_id']))
    return items


def full_run(dataset, cache):
    requests, evidence = load_context(dataset, 'full')
    result = {}
    for label, visual in (('without_visual', False), ('with_visual', True)):
        rows, diagnostics, pipeline = run(dataset, cache=cache, visual=visual)
        strict = validate_rows(rows, requests, evidence)
        loose = validate_rows(rows, requests, evidence, nonstandard_allow_unproven_incomplete=True)
        result[label] = {'rows': rows, 'diagnostics': diagnostics, 'log': pipeline.guard.log,
                         'sha256': hashlib.sha256(serialize(rows).encode()).hexdigest(),
                         'strict_errors': len(strict.errors),
                         'strict_rows': len({e.split(':')[0] for e in strict.errors}),
                         'nonstandard_errors': len(loose.errors),
                         'status': dict(sorted(Counter(r['deletion_status'] for r in rows).items())),
                         'no_finding': {c['case_id']: c for c in analyse(rows, diagnostics)},
                         'unknown_items': unknown_items(rows, diagnostics),
                         'unknown_items_all': unknown_items(rows, diagnostics, only_no_finding=False),
                         'unresolved_items': sum(len(d.get('unresolved', ())) for d in diagnostics.values())}
    rerun, _, _ = run(dataset, cache=cache, visual=True)
    base, vis = result['without_visual'], result['with_visual']
    before = {r['case_id']: r for r in base['rows']}
    after = {r['case_id']: r for r in vis['rows']}
    changed = []
    for case in sorted(before):
        if before[case] == after[case]: continue
        changed.append({'case_id': case, 'status': [before[case]['deletion_status'], after[case]['deletion_status']],
                        'steps_before': len(before[case]['steps_json']),
                        'steps_after': [[s['phase'], s['operation'], s['system_id'], s['resource_id'], s['evidence_id']]
                                        for s in after[case]['steps_json']],
                        'basis_after': vis['diagnostics'][case].get('status_basis')})
    reassessed = []
    for case, entry in sorted(base['no_finding'].items()):
        now = vis['no_finding'].get(case)
        reassessed.append({'case_id': case, 'shape_before': entry['category'],
                           'after': 'has an evidenced finding' if now is None else now['category'],
                           'changed': before[case] != after[case],
                           'unresolved_after': dict(now['classes']) if now else {}})
    image_ids = {e.meta['file_id'] for e in load_visual(dataset).extractions}
    image_citations = [e for e in vis['log'] if e['evidence_id'] in image_ids]
    return {
        'sha256': {'without_visual': base['sha256'], 'with_visual': vis['sha256'],
                   'with_visual_rerun': hashlib.sha256(serialize(rerun).encode()).hexdigest()},
        'status': {'without_visual': base['status'], 'with_visual': vis['status']},
        'strict_validator': {k: {'errors': result[k]['strict_errors'], 'rows': result[k]['strict_rows']} for k in result},
        'nonstandard_validator_errors': {k: result[k]['nonstandard_errors'] for k in result},
        'incomplete_without_findings': {k: len(result[k]['no_finding']) for k in result},
        'unresolved_items': {k: result[k]['unresolved_items'] for k in result},
        'changed_rows': changed,
        'reassessed_no_finding_rows': reassessed,
        'unknown_treatment_items': {
            'without_visual': len(base['unknown_items']), 'with_visual': len(vis['unknown_items']),
            'left_no_finding_rows': sorted(map(list, base['unknown_items'] - vis['unknown_items'])),
            'added_in_no_finding_rows': sorted(map(list, vis['unknown_items'] - base['unknown_items'])),
            # Of the baseline items, which are still undecided in any case once screenshots are used.
            'baseline_items_decided_by_visual': sorted(map(list, base['unknown_items'] - vis['unknown_items_all'])),
            'all_cases': {'without_visual': len(base['unknown_items_all']), 'with_visual': len(vis['unknown_items_all'])}},
        'image_citations': {'checked': len(image_citations), 'accepted': sum(e['accepted'] for e in image_citations),
                            'entries': image_citations},
        'citations_total': {k: {'checked': len(result[k]['log']), 'accepted': sum(e['accepted'] for e in result[k]['log'])}
                            for k in result},
    }


def extraction(dataset):
    with tempfile.TemporaryDirectory() as tmp:
        cold = load_visual(dataset, Path(tmp))
        warm = load_visual(dataset, Path(tmp))
    return {'cold': cold.counters, 'warm': warm.counters,
            'methods': dict(Counter(e.document['provenance']['method'] for e in cold.extractions if e.document)),
            'valid_json': sum(e.document is not None for e in cold.extractions), 'images': len(cold.extractions),
            'model_calls': sum(r['model_call'] for r in cold.ledger + warm.ledger),
            'input_tokens': sum(r['input_tokens'] or 0 for r in cold.ledger + warm.ledger),
            'output_tokens': sum(r['output_tokens'] or 0 for r in cold.ledger + warm.ledger),
            'observations': len(cold.observations),
            'records': cold.records, 'discrepancies': cold.discrepancies, 'unresolved_times': cold.unresolved_times}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    args = parser.parse_args()
    report = {'extraction': extraction(args.dataset), 'sample': sample_splits(args.dataset, args.cache),
              'full': full_run(args.dataset, args.cache)}
    print(json.dumps(report, indent=1, sort_keys=True, default=str))
