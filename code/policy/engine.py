"""M5 policy engine: apply deletion_rules.csv to M4 physical-copy states.

The engine decides, per subject-linked physical copy, which rule applies,
whether its condition holds at audit_at (TRUE/FALSE/UNKNOWN), the effective
action and whether the observed state complies. It does not decide flows
(M6), final step order, citations or case status (M7). Unknown states,
unmapped categories and unbound conditions are UNRESOLVED, never compliant.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ingest.evidence import parse_time
from state.engine import field_values, system_for

from .categories import classify, load_map
from .conditions import (FALSE, TRUE, UNKNOWN, Dossier, Record, evaluate, exposed_fields,
                         explicit_identifier_nulls, identity_claims, load_config, subject_from)
from .rules import PolicyTable, load_rules

COMPLIANT, VIOLATION, UNRESOLVED, DEFERRED = 'COMPLIANT', 'VIOLATION', 'UNRESOLVED', 'DEFERRED_M6'
SEVERITY = {VIOLATION: 3, UNRESOLVED: 2, COMPLIANT: 1, DEFERRED: 0}
EXISTING = ('PRESENT', 'REDACTED', 'ANONYMIZED', 'RESTORE_ENABLED', 'RESTORE_BLOCKED')
# Contract step templates (problem statement operation table), keyed by treatment.
TEMPLATES = {
    'DELETE': (('FINDING', 'REPORT_REMAINING_RECORD', 'PRESENT'),
               ('REMEDIATION', 'DELETE_RECORD', 'ABSENT'),
               ('VERIFICATION', 'VERIFY_RECORD_ABSENT', 'ABSENT')),
    'REDACT': (('FINDING', 'REPORT_EXPOSED_PII', 'PRESENT'),
               ('REMEDIATION', 'REDACT_RECORD', 'REDACTED'),
               ('VERIFICATION', 'VERIFY_RECORD_REDACTED', 'REDACTED')),
    'ANONYMIZE': (('FINDING', 'REPORT_EXPOSED_PII', 'PRESENT'),
                  ('REMEDIATION', 'ANONYMIZE_RECORD', 'ANONYMIZED'),
                  ('VERIFICATION', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED')),
    'RETAIN': ((), (), ('VERIFICATION', 'VERIFY_RECORD_PRESENT', 'PRESENT')),
    'RESTORE': (('FINDING', 'REPORT_RESTORE_RISK', 'ACTIVE'),
                ('REMEDIATION', 'BLOCK_RESTORE', 'BLOCKED'),
                ('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED')),
}


@dataclass(frozen=True)
class PolicyDecision:
    case_id: str
    user_id: str | None
    system_id: str | None
    resource_id: str | None
    topology: str | None
    observed_state: str
    state_supported: bool
    state_explanation: str
    evidence_id: str
    locator: str
    category: str | None
    category_status: str
    category_basis: str
    rule_id: str | None
    required_action: str | None
    condition: str | None
    condition_outcome: str | None
    condition_reason: str
    condition_evidence: tuple[str, ...]
    on_false: str | None
    effective_action: str | None
    exposed_fields: tuple[str, ...]
    compliance: str
    reason: str
    obligations: tuple[tuple[str, str, str], ...]
    restore_obligations: tuple[tuple[str, str, str], ...]
    attribution_conflicts: tuple[str, ...] = ()

    def as_dict(self):
        return asdict(self)


class Context:
    """Case-independent indexes over M1 observations for attribute lookups."""

    def __init__(self, observations, rules: Path | PolicyTable, category_map=None, bindings=None,
                 anomalies=frozenset()):
        self.anomalies = frozenset(anomalies)
        self.table = rules if isinstance(rules, PolicyTable) else load_rules(rules)
        self.cmap = category_map or load_map()
        self.config = bindings or load_config()
        self.by_locator = {(o.evidence_id, o.locator): o for o in observations}
        self.by_resource = defaultdict(list)
        self.documents = defaultdict(list)
        for o in observations:
            if o.source_type in ('activity', 'audit'): continue
            if o.resource_id: self.by_resource[o.resource_id].append(o)
            if o.source_type == 'pdf' and o.locator.startswith('line:'):
                self.documents[o.evidence_id].append(o)


def _attribution(o, subject) -> str:
    """Own-record attribution of a same-ID observation; a shared ID alone proves nothing."""
    return subject.attribution(identity_claims(field_values(o.raw_fields)))


def _record(o, linked) -> Record:
    return Record(o.evidence_id, o.locator, o.captured_at, field_values(o.raw_fields), linked)


def _admissible_time(ctx, o, cutoff) -> bool:
    """Evidence captured, recorded or emitted after the cutoff, or after its own
    capture, or quarantined by M1, never decides a policy condition."""
    if parse_time(o.captured_at) > cutoff or (o.evidence_id, o.locator) in ctx.anomalies:
        return False
    for stamp in (o.record_time, o.event_time):
        if stamp and (parse_time(stamp) > cutoff or parse_time(stamp) > parse_time(o.captured_at)):
            return False
    return True


def _dossier(ctx, latest, assertions, resolution, subject, category):
    """Collect admissible, subject-attributed field sets for one physical copy.

    Returns the dossier, the usable observations and the citations of linked
    observations whose identifiers contradict the subject (kept as evidence,
    never used, and reported so the assessment stays unresolved).
    """
    cutoff = parse_time(resolution.audit_at)
    linked = {}
    for a in assertions:
        if a['system_id'] == latest['system_id'] and a['resource_id'] == latest['resource_id']:
            linked[(a['evidence_id'], a['locator'])] = a.get('attribution')
    seen, observations, conflicts = set(), [], set()
    for key, strength in sorted(linked.items(), key=lambda item: item[0]):
        o = ctx.by_locator.get(key)
        if not o or o.source_type in ('activity', 'audit'): continue
        seen.add(key)
        if not _admissible_time(ctx, o, cutoff): continue
        # M2/M4 links are re-checked against every identifier the record names.
        verdict = _attribution(o, subject)
        if verdict == 'FOREIGN' or strength == 'mixed_context':
            conflicts.add(f'{o.evidence_id}:{o.locator}'); continue
        # An identifier-free record is usable only through an explicit trace join.
        if verdict == 'UNATTRIBUTED' and strength != 'correlated': continue
        observations.append((o, True))
    for o in ctx.by_resource.get(latest['resource_id'], ()):
        key = (o.evidence_id, o.locator)
        if key in seen or system_for(o) != latest['system_id']: continue
        if not _admissible_time(ctx, o, cutoff): continue
        # Other copies (including other topologies) count only when the record
        # itself names this subject and nobody else, as of the audit cutoff.
        if _attribution(o, subject) != 'SUBJECT': continue
        observations.append((o, False)); seen.add(key)
    observations.sort(key=lambda pair: (parse_time(pair[0].captured_at), pair[0].evidence_id, pair[0].locator),
                      reverse=True)
    usable = {(o.evidence_id, o.locator) for o, _ in observations}
    current = ctx.by_locator.get((latest['evidence_id'], latest['locator']))
    if current and (current.evidence_id, current.locator) not in usable:
        current = None
    documents = []
    for evidence_id, lines in sorted(ctx.documents.items()):
        if not lines or any(not _admissible_time(ctx, l, cutoff) for l in lines): continue
        texts = [l.raw_fields.get('text', '') for l in sorted(lines, key=lambda l: int(l.locator.split(':')[1]))]
        if any(latest['resource_id'] in t for t in texts):
            documents.append((evidence_id, texts))
    dossier = Dossier(category or '', latest['state'], resolution.audit_at, subject,
                      _record(current, True) if current and latest['supported'] else None,
                      [_record(o, linked) for o, linked in observations], documents, latest['resource_id'])
    return dossier, [o for o, _ in observations], tuple(sorted(conflicts))


def _comply(action, state, exposure, dossier, config):
    """Return (compliance, reason, obligations) for an effective action and state."""
    template = TEMPLATES[action]
    verify = (template[2],)
    if state == 'UNKNOWN':
        return UNRESOLVED, 'M4 state is unresolved', ()
    if action == 'DELETE':
        if state == 'ABSENT': return COMPLIANT, 'record absent as required', verify
        return VIOLATION, f'record must be deleted but is {state}', template
    if action == 'RETAIN':
        if state in EXISTING: return COMPLIANT, 'policy-required record retained', verify
        return UNRESOLVED, 'policy-required record is not available; no allowed step restores it', ()
    # REDACT / ANONYMIZE keep the record but remove identifiers.
    if state == 'ABSENT':
        if action == 'ANONYMIZE':
            return COMPLIANT, 'record no longer exists, so it cannot be linked', (TEMPLATES['DELETE'][2],)
        return UNRESOLVED, 'record whose context must be retained is absent', ()
    if exposure:
        return VIOLATION, 'identifiers still exposed: ' + ','.join(exposure), template
    current = dossier.current
    if current and (explicit_identifier_nulls(current.fields, config) or
                    any(str(v).strip() in config['redaction_markers'] for v in current.fields.values())):
        return COMPLIANT, 'identifier fields observed removed', verify
    return UNRESOLVED, 'no field-level evidence that identifiers were removed', ()


def decide_copy(ctx: Context, latest: dict, assertions: list[dict], resolution, subject) -> PolicyDecision:
    decision, conflicts = _decide_copy(ctx, latest, assertions, resolution, subject)
    if not conflicts:
        return decision
    # Contradictory attribution: keep the evidence, never decide from it.
    compliance = decision.compliance if decision.compliance == DEFERRED else UNRESOLVED
    return replace(decision, compliance=compliance, attribution_conflicts=conflicts,
                   obligations=() if compliance == UNRESOLVED else decision.obligations,
                   restore_obligations=() if compliance == UNRESOLVED else decision.restore_obligations,
                   reason=('linked evidence names another person: ' + ', '.join(conflicts)
                           if compliance == UNRESOLVED else decision.reason))


def _decide_copy(ctx, latest, assertions, resolution, subject):
    base = dict(case_id=resolution.case_id, user_id=resolution.user_id, system_id=latest['system_id'],
                resource_id=latest['resource_id'], topology=latest['topology'],
                observed_state=latest['state'], state_supported=latest['supported'],
                state_explanation=latest['explanation'], evidence_id=latest['evidence_id'],
                locator=latest['locator'])
    _, observations, conflicts = _dossier(ctx, latest, assertions, resolution, subject, None)
    category = classify(observations, latest['system_id'], latest['resource_id'],
                        ctx.table.categories, ctx.cmap)
    dossier, _, _ = _dossier(ctx, latest, assertions, resolution, subject, category.category)
    empty = dict(rule_id=None, required_action=None, condition=None, condition_outcome=None,
                 condition_reason='', condition_evidence=(), on_false=None, effective_action=None,
                 exposed_fields=(), obligations=(), restore_obligations=())
    common = dict(base, category=category.category, category_status=category.status,
                  category_basis=category.basis)
    if category.status == 'PROCESS':
        return PolicyDecision(**common, **dict(empty, compliance=DEFERRED,
                              reason='process resource; active-flow policy belongs to M6')), conflicts
    rule = ctx.table.rule_for(category.category) if category.status == 'MAPPED' else None
    if rule is None:
        why = {'AMBIGUOUS': 'conflicting category signals', 'UNMAPPED': 'no policy category for observed signals'}
        return PolicyDecision(**common, **dict(empty, compliance=UNRESOLVED,
                              reason=why.get(category.status, 'no rule for category'))), conflicts
    result, binding = evaluate(rule, dossier, ctx.config)
    on_false = binding['on_false'] if binding else None
    permitted = tuple(ctx.config['permitted_fields'].get(rule.data_category, ()))
    exposure = (exposed_fields(dossier.current.fields, subject, ctx.config, permitted)
                if dossier.current else ())
    action, restore = None, ()
    if result.outcome == TRUE:
        action = rule.required_action
    elif result.outcome == FALSE and on_false == 'TARGET_SATISFIED':
        action = rule.required_action
    elif result.outcome == FALSE and on_false == 'DEFAULT_ERASURE':
        action = 'DELETE'
    fields = dict(rule_id=rule.rule_id, required_action=rule.required_action, condition=rule.condition,
                  condition_outcome=result.outcome, condition_reason=result.reason,
                  condition_evidence=result.evidence, on_false=on_false, effective_action=action,
                  exposed_fields=exposure)
    if action is None:
        why = ('condition is UNKNOWN at audit_at' if result.outcome == UNKNOWN
               else 'condition FALSE and no supplied rule decides the treatment')
        return PolicyDecision(**common, **fields, compliance=UNRESOLVED, reason=why,
                              obligations=(), restore_obligations=()), conflicts
    if result.outcome == FALSE and on_false == 'TARGET_SATISFIED' and latest['state'] != 'UNKNOWN':
        # The predicate itself established, from observed fields, that the
        # identifiability this action removes is already gone.
        compliance, reason = COMPLIANT, 'condition FALSE: target treatment already holds'
        obligations = ((TEMPLATES[action][2],) if latest['state'] in EXISTING
                       else (TEMPLATES['DELETE'][2],))
    else:
        compliance, reason, obligations = _comply(action, latest['state'], exposure, dossier, ctx.config)
    # A retained backup stays; its restore permission is assessed separately.
    if latest['state'] == 'RESTORE_ENABLED':
        restore = TEMPLATES['RESTORE']
    elif latest['state'] == 'RESTORE_BLOCKED':
        restore = (TEMPLATES['RESTORE'][2],)
    if restore and action == 'RETAIN':
        obligations = ()
    return PolicyDecision(**common, **fields, compliance=compliance, reason=reason,
                          obligations=obligations, restore_obligations=restore), conflicts


def rollup(decisions: list[PolicyDecision]) -> list[dict]:
    """One logical resource per (system, resource); the worst physical copy decides."""
    groups = defaultdict(list)
    for d in decisions:
        groups[(d.system_id or '', d.resource_id or '')].append(d)
    output = []
    for (system, resource), copies in sorted(groups.items()):
        worst = max(copies, key=lambda d: (SEVERITY[d.compliance], bool(d.restore_obligations and
                                           d.restore_obligations[0][0] == 'FINDING'), d.topology or ''))
        restore_risk = any(d.restore_obligations and d.restore_obligations[0][0] == 'FINDING' for d in copies)
        output.append({'system_id': system, 'resource_id': resource,
                       'category': worst.category, 'rule_id': worst.rule_id,
                       'effective_action': worst.effective_action, 'compliance': worst.compliance,
                       'restore_risk': restore_risk, 'copies': len(copies),
                       'deciding_copy': {'topology': worst.topology, 'evidence_id': worst.evidence_id,
                                         'locator': worst.locator, 'state': worst.observed_state},
                       'obligations': worst.obligations,
                       'restore_obligations': next((d.restore_obligations for d in copies
                                                    if d.restore_obligations and restore_risk ==
                                                    (d.restore_obligations[0][0] == 'FINDING')), ())})
    return output


def decide_case(ctx: Context, case_state: dict, resolution) -> dict:
    subject = subject_from(resolution) if resolution.user_id else None
    decisions = []
    if subject:
        for latest in case_state['latest']:
            decisions.append(decide_copy(ctx, latest, case_state['assertions'], resolution, subject))
    resources = rollup(decisions)
    return {'case_id': case_state['case_id'], 'user_id': case_state['user_id'],
            'audit_at': case_state['audit_at'],
            'decisions': [d.as_dict() for d in decisions], 'resources': resources}
