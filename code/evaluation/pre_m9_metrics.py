"""Evaluation-only pre-M9 remediation metrics; this module reads sample gold. Production code never imports it.

    python3 code/evaluation/pre_m9_metrics.py > code/evaluation/checkpoints/PRE_M9_METRICS.json

Reports, for the remediated pipeline:

* two independent 518-case runs (hash equality), the ``--no-visual`` ablation
  and the M8 / M7 reference hashes;
* the strict M0 validator (errors, affected rows) and the NONSTANDARD
  diagnostic validator, with every strict-invalid case assigned a primary
  cause class (Phase 5): 1 correctable implementation defect, 2 missed
  admissible evidence, 3 incorrect policy interpretation, 4 genuine missing
  evidence, 5 irreducible uncertainty under the participant contract;
* status distribution, UNKNOWN treatment counts, citation guard totals;
* sample metrics per split (dev = first 22, holdout = last 10, report-only
  and not blind) with every missed or extra step and a general miss cause;
* cross-customer contamination and negative safety probes on the 518 rows;
* the model-call ledger (M3 offline rules, M8 manual fixtures).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import load_context, read_output, validate_rows
from evaluation.m7_metrics import summary
from evaluation.m8_metrics import unknown_items
from evaluation.scorer import key, score_rows
from ingest.evidence import parse_time
from policy.conditions import identity_claims, subject_from
from synthesis.main import Pipeline, serialize
from synthesis.reports import analyse, reason_class

ROOT = Path(__file__).resolve().parents[2]
M8_FINAL_SHA = 'a45cdcf0f2ca24b51c193ba9e39b208744fbc6d4914c2201e19e1f99a3ac44df'   # merged M8 (cccb59e)
M7_SHA = 'aeb5c135'
RESOURCE = re.compile(r'\b(?:account|support|analytics|audit_record|search|backup|export|data_flow|cache|'
                      r'tombstone|legal_hold|email_delivery|marketing|telemetry)_\d+\b')
# Conditions that need a supplied fact the participant data does not carry
# (cause 5), versus conditions on record content that was not observed (cause 4).
SUPPLIED_FACT_RULES = {'rule_12': 'no supplied retention period covering audit_at',
                       'rule_13': 'no supplied active legal hold with a basis'}
CONTENT_RULES = {'rule_05': 'conversation content not observed (shared-context condition undecidable)',
                 'rule_06': 'attachment ownership not observed',
                 'rule_07': 'no evidence of irreversible anonymization or of remaining identifiers',
                 'rule_08': 'no evidence of irreversible anonymization or of remaining identifiers',
                 'rule_11': 'log content not observed',
                 'rule_14': 'no explicit restore control observed',
                 'rule_15': 'account status not observed'}


def execute(dataset, cache, sample=False, visual=True):
    pipeline = Pipeline(dataset, sample, cache, visual)
    rows, diagnostics, meta = [], {}, {}
    for request in pipeline.requests():
        row, diag, info = pipeline.case(request)
        rows.append(row)
        diagnostics[row['case_id']] = diag
        meta[row['case_id']] = info
    return rows, diagnostics, meta, pipeline


def sha(rows):
    return hashlib.sha256(serialize(rows).encode()).hexdigest()


def blocker_classes(case_id, row, diag, info):
    """Primary cause class and every blocker (class, kind, resource, detail) of one strict-invalid case."""
    if info.get('resolution') != 'resolved':
        return 4, [(4, 'identity not resolved', '', f'identity {info.get("resolution")}')]
    records = {(i['system_id'], i['resource_id']): i for i in diag.get('items', ()) if i['kind'] == 'record'}
    if not diag.get('items'):
        return 4, [(4, 'no admissibly linked subject-owned resource or process', '', '')]
    blockers = []
    for u in diag.get('unresolved', ()):
        rule = records.get((u['system_id'], u['resource_id']), {}).get('rule_id')
        label = reason_class(u['reason'])
        where = f'{u["system_id"]}/{u["resource_id"]}'
        if label == 'unknown conditional treatment' and rule in SUPPLIED_FACT_RULES:
            blockers.append((5, f'{rule}: {SUPPLIED_FACT_RULES[rule]}', where, u['reason']))
        elif label == 'unknown conditional treatment':
            blockers.append((4, f'{rule}: {CONTENT_RULES.get(rule, "condition undecided")}', where, u['reason']))
        elif label == 'unknown state':
            blockers.append((4, 'treatment decided; no admissible reading of the current state', where, u['reason']))
        elif label == 'missing policy mapping':
            blockers.append((4, 'no category signal in participant evidence', where, u['reason']))
        elif label == 'contested attribution':
            blockers.append((5, 'linked evidence names another person', where, u['reason']))
        elif label == 'process state unknown':
            blockers.append((4, 'process safe state shown only by inventory or not at all', where, u['reason']))
        elif label == 'retained record not observed':
            blockers.append((4, 'policy-retained record not observed', where, u['reason']))
        else:
            blockers.append((1, label, where, u['reason']))
    if not blockers:
        return 1, [(1, 'strict-invalid with no unresolved item', '', '')]
    # The case is decidable only if every blocker is; the weakest class decides.
    return max(b[0] for b in blockers), blockers


def full_section(dataset, cache):
    requests, evidence = load_context(dataset, 'full')
    rows, diagnostics, meta, pipeline = execute(dataset, cache)
    rerun, _, _, _ = execute(dataset, cache)
    ablation, _, _, _ = execute(dataset, cache, visual=False)
    strict = validate_rows(rows, requests, evidence)
    loose = validate_rows(rows, requests, evidence, nonstandard_allow_unproven_incomplete=True)
    invalid = sorted({e.split(':')[0] for e in strict.errors})
    by_row = {r['case_id']: r for r in rows}
    partition, causes, blockers = {}, Counter(), Counter()
    for case_id in invalid:
        cls, found = blocker_classes(case_id, by_row[case_id], diagnostics[case_id], meta[case_id])
        partition[case_id] = {'class': cls, 'status': by_row[case_id]['deletion_status'],
                              'steps': len(by_row[case_id]['steps_json']),
                              'errors': [e.split(':', 1)[1].strip() for e in strict.errors
                                         if e.split(':')[0] == case_id],
                              'blockers': [{'class': c, 'kind': k, 'resource': w, 'reason': r}
                                           for c, k, w, r in found]}
        causes[cls] += 1
        for b in found:
            blockers[f'class {b[0]}: {b[1]}'] += 1
    audit_partition = Counter()
    for case_id in invalid:
        d = diagnostics[case_id]
        if meta[case_id].get('resolution') != 'resolved' or not d.get('items'):
            audit_partition['no admissibly linked subject-owned resource'] += 1
        elif any(reason_class(u['reason']) == 'missing policy mapping' for u in d.get('unresolved', ())):
            audit_partition['unmapped records'] += 1
        else:
            audit_partition['unresolved treatment, state or process evidence'] += 1
    log = pipeline.guard.log
    shapes = Counter(c['category'] for c in analyse(rows, diagnostics))
    return rows, diagnostics, meta, pipeline, {
        'sha256': {'run_1': sha(rows), 'run_2': sha(rerun), 'identical': sha(rows) == sha(rerun),
                   'no_visual_ablation': sha(ablation), 'm8_final_reference': M8_FINAL_SHA,
                   'equals_m8_final': sha(rows) == M8_FINAL_SHA,
                   'no_visual_equals_m7_prefix': sha(ablation).startswith(M7_SHA)},
        'status': dict(sorted(Counter(r['deletion_status'] for r in rows).items())),
        'strict_validator': {'valid': strict.valid, 'errors': len(strict.errors), 'rows': len(invalid)},
        'nonstandard_diagnostic_validator': {'valid': loose.valid, 'errors': len(loose.errors)},
        'incomplete_empty': sum(1 for r in rows if r['deletion_status'] == 'INCOMPLETE' and not r['steps_json']),
        'incomplete_without_findings': sum(1 for r in rows if r['deletion_status'] == 'INCOMPLETE'
                                           and r['steps_json'] and
                                           not any(s['phase'] == 'FINDING' for s in r['steps_json'])),
        'incomplete_without_findings_by_shape': dict(sorted(shapes.items())),
        'strict_invalid_audit_partition': dict(sorted(audit_partition.items())),
        'strict_invalid_cause_classes': {str(k): v for k, v in sorted(causes.items())},
        'strict_invalid_blockers': dict(sorted(blockers.items())),
        'strict_invalid_cases': partition,
        'unknown_treatment_items': {'in_no_finding_rows': len(unknown_items(rows, diagnostics)),
                                    'all_cases': len(unknown_items(rows, diagnostics, only_no_finding=False))},
        'unresolved_items': sum(len(d.get('unresolved', ())) for d in diagnostics.values()),
        'm4_unknown_latest': sum(d.get('m4_unknown_latest', 0) for d in diagnostics.values()),
        'linked_resources': sum(len(d.get('items', ())) for d in diagnostics.values()),
        'citations': {'checked': len(log), 'accepted': sum(e['accepted'] for e in log),
                      'rejected': sum(not e['accepted'] for e in log),
                      'rejection_reasons': dict(sorted(Counter(e['reason'] for e in log
                                                               if not e['accepted']).items()))},
        'excluded_visual': {c: d['excluded_visual'] for c, d in sorted(diagnostics.items())
                            if d.get('excluded_visual')},
        'safety': safety(rows, diagnostics, meta, pipeline),
    }


def safety(rows, diagnostics, meta, pipeline):
    """Cross-customer contamination and negative safety probes on the 518 rows."""
    owners = defaultdict(set)
    for r in rows:
        for s in r['steps_json']:
            owners[(s['system_id'], s['resource_id'])].add(meta[r['case_id']].get('user_id'))
    shared = sorted(f'{k[0]}/{k[1]}' for k, v in owners.items() if len(v) > 1)
    unsafe_delete, anonymized_unproven, retained_deleted = [], [], []
    for r in rows:
        items = {(i['system_id'], i['resource_id']): i for i in diagnostics[r['case_id']].get('items', ())}
        for s in r['steps_json']:
            item = items.get((s['system_id'], s['resource_id']), {})
            if s['operation'] == 'DELETE_RECORD' and item.get('category') in (
                    'SECURITY_AUDIT_LOG', 'LEGAL_HOLD_RECORD', 'BACKUP_ARCHIVE', 'ACCOUNT_TOMBSTONE',
                    'SUPPORT_MESSAGE') and item.get('effective_action') != 'DELETE':
                unsafe_delete.append(f'{r["case_id"]}:{s["resource_id"]}')
            if s['operation'] == 'DELETE_RECORD' and item.get('effective_action') == 'RETAIN':
                retained_deleted.append(f'{r["case_id"]}:{s["resource_id"]}')
            if s['operation'] == 'VERIFY_RECORD_ANONYMIZED' and s['evidence_id']:
                anonymized_unproven.append(f'{r["case_id"]}:{s["resource_id"]}')
    compliant_anonymize = 0
    for d in diagnostics.values():
        for i in d.get('items', ()):
            if i.get('effective_action') == 'ANONYMIZE' and i.get('compliance') == 'COMPLIANT':
                compliant_anonymize += 1
    guard_foreign = [e for e in pipeline.guard.log if e['accepted'] and 'another person' in e['reason']]
    return {'resources_in_steps_of_more_than_one_user': shared,
            'delete_without_decided_delete_treatment': unsafe_delete,
            'delete_of_policy_retained_record': retained_deleted,
            'cited_anonymized_verifications': anonymized_unproven,
            'compliant_anonymize_items': compliant_anonymize,
            'accepted_citations_naming_another_person': len(guard_foreign)}


def miss_cause(step, case_id, diag, pipeline, request, gold_case_ids):
    """General cause of a missed gold step, from participant evidence only."""
    target = (step['system_id'], step['resource_id'])
    if any((i['system_id'], i['resource_id']) == target for i in diag.get('items', ())):
        for u in diag.get('unresolved', ()):
            if (u['system_id'], u['resource_id']) == target:
                return 'linked: ' + reason_class(u['reason'])
        return 'linked: planned with a different treatment or phase'
    resolution = pipeline.graph.resolve(request)
    subject = subject_from(resolution)
    cutoff = parse_time(resolution.audit_at)
    mentions = [o for o in pipeline.mentions.get(step['resource_id'], ())]
    records = [o for o in mentions if o.source_type not in ('activity', 'audit')]
    admissible = [o for o in records if parse_time(o.captured_at) <= cutoff]
    verdicts = {subject.attribution(identity_claims(o.raw_fields)) for o in admissible}
    if 'SUBJECT' in verdicts:
        return 'MISSED: admissible evidence names the subject'
    if admissible and verdicts == {'UNATTRIBUTED'}:
        return 'unlinked: only identifier-free records (positional or naming joins are not ownership)'
    if admissible:
        return 'unlinked: records name another person or none'
    if records:
        return 'unlinked: mentioned only in evidence captured after audit_at'
    if mentions:
        return 'unlinked: mentioned only in workflow activity rows (claims)'
    return 'unlinked: no participant evidence mentions the resource'


def sample_section(dataset, cache):
    gold = {r['case_id']: r for r in read_output(dataset / 'sample_output.csv')}
    requests, evidence = load_context(dataset, 'sample')
    ordered = sorted(gold)
    splits = {'dev': ordered[:22], 'holdout': ordered[22:], 'all': ordered}
    out = {}
    for label, visual in (('with_visual', True), ('without_visual', False)):
        rows, diagnostics, _, pipeline = execute(dataset, cache, sample=True, visual=visual)
        pred = {r['case_id']: r for r in rows}
        out[label] = {split: summary(score_rows([pred[i] for i in ids], [gold[i] for i in ids], evidence, requests))
                      for split, ids in splits.items()}
        if not visual: continue
        pipeline.mentions = defaultdict(list)
        for o in pipeline.evidence.observations:
            for resource in set(RESOURCE.findall(json.dumps(o.raw_fields, default=str))):
                pipeline.mentions[resource].append(o)
        reqs = {r['case_id']: r for r in pipeline.requests()}
        misses, extras, causes, by_operation = {}, {}, Counter(), Counter()
        for case_id in ordered:
            split = 'dev' if case_id in splits['dev'] else 'holdout'
            remaining = Counter(map(key, pred[case_id]['steps_json']))
            for s in gold[case_id]['steps_json']:
                if remaining[key(s)] > 0:
                    remaining[key(s)] -= 1; continue
                cause = miss_cause(s, case_id, diagnostics[case_id], pipeline, reqs[case_id], ordered)
                misses.setdefault(case_id, []).append({'step': list(key(s)), 'cause': cause})
                causes[(split, cause)] += 1
                by_operation[(split, s['phase'], s['operation'])] += 1
            golden = Counter(map(key, gold[case_id]['steps_json']))
            for s in pred[case_id]['steps_json']:
                if golden[key(s)] > 0:
                    golden[key(s)] -= 1; continue
                extras.setdefault(case_id, []).append(list(key(s)))
        out['misses'] = misses
        out['extras'] = extras
        out['miss_causes'] = {f'{s}: {c}': n for (s, c), n in sorted(causes.items())}
        out['misses_by_operation'] = {f'{s}: {p} {o}': n for (s, p, o), n in sorted(by_operation.items())}
        out['status_mismatches'] = {c: [gold[c]['deletion_status'], pred[c]['deletion_status']]
                                    for c in ordered if gold[c]['deletion_status'] != pred[c]['deletion_status']}
    return out


def ledger(pipeline):
    visual = pipeline.visual
    return {'runtime_model_calls': (visual.counters.get('model_calls', 0) if visual else 0),
            'input_tokens': 0 if not visual else sum(r['input_tokens'] or 0 for r in visual.ledger),
            'output_tokens': 0 if not visual else sum(r['output_tokens'] or 0 for r in visual.ledger),
            'cost_usd': 0.0, 'intent_mode': 'offline rules (no provider configured)',
            'intent_requests_routed_to_unconfigured_model': len(pipeline.classifier.routed),
            'intent_model_calls': 0 if pipeline.classifier.model_call is None else None,
            'screenshot_extraction': 'committed manual fixtures'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    args = parser.parse_args()
    _, _, _, pipeline, full = full_section(args.dataset, args.cache)
    report = {'full': full, 'sample': sample_section(args.dataset, args.cache), 'usage': ledger(pipeline)}
    print(json.dumps(report, indent=1, sort_keys=True, default=str))
