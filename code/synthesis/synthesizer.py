"""M7 case decisions and steps_json from typed M5/M6 (+ M7 risk) decisions.

Case status:

* NOT_APPLICABLE: the request does not authorise deletion (M3); ``[]``.
* COMPLETE: the subject resolved, at least one relevant resource or process
  was found, every record copy is COMPLIANT, every process is proved safe,
  nothing is UNRESOLVED/UNKNOWN/CONFLICTING, and every verification citation
  passes the citation guard. No resources is never COMPLETE.
* INCOMPLETE: anything else. Findings cite guarded evidence; remediation and
  post-remediation verification carry an empty evidence_id.

Steps are generated only from typed decisions:

* VIOLATION record -> finding / remediation / verification template of its
  effective action (M5 TEMPLATES).
* COMPLIANT record -> its verification (cited in a COMPLETE case, future
  check in an INCOMPLETE case).
* UNRESOLVED record whose required treatment is decided (rule mapped,
  condition decided, all copies agree, no contested attribution) and whose
  only gap is its current state -> the future verification of that treatment
  in an INCOMPLETE case. No finding or remediation: its current state is not
  proven. Every other UNRESOLVED record yields no step and stays in
  diagnostics.
* M6 process -> its M6 obligation template; UNKNOWN/CONFLICTING -> none.
"""
from __future__ import annotations

from intent.classifier import DELETE
from policy.engine import TEMPLATES

from .ordering import apply_dependencies, canonical_key, renumber

# Unresolved reasons that leave only the current state open, not the treatment.
STATE_ONLY_GAPS = {'M4 state is unresolved', 'no field-level evidence that identifiers were removed'}
RISK = {'ACTIVE', 'RESTORE_ENABLED'}


def _future_target(resource):
    """The decided target verification of an UNRESOLVED record, or (None, why)."""
    copies = [c for c in resource['copy_decisions'] if c['compliance'] != 'DEFERRED_M6']
    if any(c['attribution_conflicts'] for c in copies):
        return None, 'contested attribution'
    actions = {c['effective_action'] for c in copies}
    if None in actions or len(actions) != 1:
        return None, 'required treatment undecided: ' + '; '.join(sorted({c['reason'] for c in copies
                                                                             if not c['effective_action']}))
    for c in copies:
        if c['compliance'] == 'UNRESOLVED' and c['reason'] not in STATE_ONLY_GAPS:
            return None, c['reason']
    return TEMPLATES[actions.pop()][2], None


def _provenance(resource, finding=False):
    deciding = resource['deciding_copy']
    copy = next((c for c in resource['copy_decisions'] if c['evidence_id'] == deciding['evidence_id']
                 and c['locator'] == deciding['locator'] and c['topology'] == deciding['topology']), None)
    risk = deciding.get('risk')
    if finding and risk:
        return {'kind': 'risk', 'evidence_id': risk['evidence_id'], 'locator': risk['locator'],
                'scope': deciding['topology']}
    return {'kind': 'm4', 'evidence_id': deciding['evidence_id'], 'locator': deciding['locator'],
            'scope': deciding['topology'],
            'category': resource['category'],
            'redaction_observed': bool(copy and copy['compliance'] == 'COMPLIANT'
                                       and copy['effective_action'] in ('REDACT', 'ANONYMIZE')),
            # F-02: only M5's corroborated anonymization (never null columns alone).
            'anonymization_proven': bool(copy and copy['compliance'] == 'COMPLIANT'
                                         and copy['effective_action'] == 'ANONYMIZE'),
            'm2_correlated': bool(copy and copy.get('_attribution') == 'correlated')}


def _future_record(resource, target):
    """Why a future-only check exists and why nothing else is emitted for it."""
    copies = [c for c in resource['copy_decisions'] if c['compliance'] != 'DEFERRED_M6']
    return {
        'operation': target[1],
        'identity_sources': sorted({f"{c['evidence_id']}:{c['locator']} ({c.get('_attribution') or 'referenced'})"
                                    for c in copies}),
        'rule_id': resource['rule_id'], 'required_treatment': resource['effective_action'],
        'condition_outcomes': sorted({c['condition_outcome'] or '' for c in copies}),
        'current_state_known': False,
        'copy_states': sorted({f"{c['topology']}:{c['observed_state']}" for c in copies}),
        'omitted': 'no admissible, subject-owned reading proves the record present, exposed or compliant, so a '
                   'finding or remediation would assert an unproven state',
        'strict_contract': 'valid only if the case also has an evidenced finding; otherwise the row is '
                           'INCOMPLETE without FINDING/REMEDIATION and fails the strict M0 plan shape',
    }


def plan(case):
    """Typed per-resource plan items before status, citations and order."""
    items, unresolved, violations = [], [], 0
    process = {(a['system_id'], a['resource_id']): a for a in case['flows'] + case['restores']}
    for r in case['resources']:
        key = (r['system_id'], r['resource_id'])
        if r['compliance'] == 'DEFERRED_M6': continue
        if key in process:
            # The archive record itself is retained (M5); restore access is M6's.
            m6 = process[key]
            reasons = {c['reason'] for c in r['copy_decisions']}
            if not (r['compliance'] in ('UNRESOLVED', 'VIOLATION') and
                    not (r['compliance'] == 'UNRESOLVED' and m6['supported'] and reasons <= {'M4 state is unresolved'})):
                continue
        entry = {'kind': 'record', 'system_id': r['system_id'], 'resource_id': r['resource_id'],
                 'compliance': r['compliance'], 'category': r['category'], 'rule_id': r['rule_id'],
                 'effective_action': r['effective_action'], 'copies': r['copies'], 'steps': []}
        if r['compliance'] == 'VIOLATION':
            violations += 1
            for phase, op, state in r['obligations']:
                entry['steps'].append({'phase': phase, 'operation': op, 'state': state,
                                       'cite': 'finding' if phase == 'FINDING' else 'never',
                                       'provenance': _provenance(r, finding=phase == 'FINDING')})
        elif r['compliance'] == 'COMPLIANT':
            for phase, op, state in r['obligations']:
                entry['steps'].append({'phase': phase, 'operation': op, 'state': state, 'cite': 'complete',
                                       'provenance': _provenance(r)})
        else:
            target, why = _future_target(r)
            entry['unresolved_reason'] = why or 'current state unproven; treatment decided'
            unresolved.append({'system_id': r['system_id'], 'resource_id': r['resource_id'],
                               'reason': entry['unresolved_reason'],
                               'copies': [{'topology': c['topology'], 'state': c['observed_state'],
                                           'reason': c['reason'], 'evidence_id': c['evidence_id']}
                                          for c in r['copy_decisions']]})
            if target:
                entry['steps'].append({'phase': target[0], 'operation': target[1], 'state': target[2],
                                       'cite': 'never', 'provenance': None})
                entry['future_only'] = _future_record(r, target)
        items.append(entry)
    for key, a in sorted(process.items()):
        entry = {'kind': a['kind'], 'system_id': a['system_id'], 'resource_id': a['resource_id'],
                 'compliance': a['status'], 'steps': []}
        if not a['supported']:
            unresolved.append({'system_id': a['system_id'], 'resource_id': a['resource_id'],
                               'reason': f'M6 {a["status"]}: {a["reason"]}', 'copies': []})
        else:
            violations += a['status'] in RISK
            for o in a['obligations']:
                cite = 'finding' if o['phase'] == 'FINDING' else ('complete' if o['basis'] == 'observed' else 'never')
                entry['steps'].append({'phase': o['phase'], 'operation': o['operation'], 'state': o['state'],
                                       'cite': cite, 'provenance': {'kind': 'm6',
                                       'evidence_id': a['deciding']['evidence_id'],
                                       'locator': a['deciding']['locator']} if a['deciding'] else None})
        items.append(entry)
    return items, unresolved, violations


def synthesize(case, guard, resolution, subject, edges=()):
    """Return (row, diagnostics) for one case view."""
    cid = case['case_id']
    if case['intent'] != DELETE:
        return {'case_id': cid, 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []}, {
            'status_basis': 'request does not authorise deletion', 'intent': case['intent']}
    diagnostics = {'citations_rejected': [], 'unresolved': [], 'dependency_report': None}
    if resolution.status != 'resolved':
        diagnostics['status_basis'] = f'identity {resolution.status}; completeness cannot be proven'
        return {'case_id': cid, 'deletion_status': 'INCOMPLETE', 'steps_json': []}, diagnostics
    items, unresolved, violations = plan(case)
    diagnostics['unresolved'] = unresolved
    # Findings must survive the guard; a rejected finding leaves the record
    # unproven (future verification only), never an uncited finding.
    for item in items:
        finding = next((s for s in item['steps'] if s['phase'] == 'FINDING'), None)
        if finding is None: continue
        step = _step(item, finding, finding['provenance']['evidence_id'] if finding['provenance'] else '')
        verdict = guard.check(cid, step, finding['provenance'], resolution, subject)
        if not verdict.accepted:
            diagnostics['citations_rejected'].append({**step, 'reason': verdict.reason})
            item['steps'] = [s for s in item['steps'] if s['phase'] == 'VERIFICATION']
            for s in item['steps']: s['cite'] = 'never'
            violations -= 1
            unresolved.append({'system_id': item['system_id'], 'resource_id': item['resource_id'],
                               'reason': f'finding citation rejected: {verdict.reason}', 'copies': []})
    found_anything = bool(items)
    complete = found_anything and not unresolved and violations == 0
    if complete:
        steps = []
        for item in items:
            for s in item['steps']:
                step = _step(item, s, s['provenance']['evidence_id'] if s['provenance'] else '')
                verdict = guard.check(cid, step, s['provenance'], resolution, subject)
                if not verdict.accepted:
                    diagnostics['citations_rejected'].append({**step, 'reason': verdict.reason})
                    complete = False
                steps.append(step)
    if complete:
        diagnostics['status_basis'] = 'every relevant copy and process proved compliant at audit_at'
    else:
        diagnostics['status_basis'] = ('no subject-linked resource or process found' if not found_anything else
                                       'outstanding remediation' if violations > 0 else
                                       'unresolved uncertainty prevents proving completeness')
        steps = []
        for item in items:
            for s in item['steps']:
                cited = s['cite'] == 'finding'
                steps.append(_step(item, s, s['provenance']['evidence_id'] if cited else ''))
    unique = {}
    for s in steps:
        unique.setdefault(canonical_key(s), s)
    ordered, report = apply_dependencies(list(unique.values()), edges)
    diagnostics['dependency_report'] = report
    diagnostics['items'] = [{k: v for k, v in i.items() if k != 'steps'} for i in items]
    emitted = {(s['operation'], s['system_id'], s['resource_id']) for s in ordered}
    diagnostics['future_only'] = [dict(i['future_only'], system_id=i['system_id'], resource_id=i['resource_id'])
                                  for i in items if i.get('future_only') and
                                  (i['future_only']['operation'], i['system_id'], i['resource_id']) in emitted]
    return {'case_id': cid, 'deletion_status': 'COMPLETE' if complete else 'INCOMPLETE',
            'steps_json': renumber(ordered)}, diagnostics


def _step(item, s, evidence_id):
    return {'step_no': 0, 'phase': s['phase'], 'system_id': item['system_id'], 'resource_id': item['resource_id'],
            'operation': s['operation'], 'state': s['state'], 'evidence_id': evidence_id}
