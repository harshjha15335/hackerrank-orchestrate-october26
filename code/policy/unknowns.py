"""Root-cause classification of M4 latest assertions that remain UNKNOWN."""
from __future__ import annotations

import re

from state.engine import READBACK_EVENTS

CAUSES = ('unsupported_source_scope', 'timestamp_anomaly', 'insufficient_identity_attribution',
          'conflicting_facts', 'missing_field_level_state', 'operational_claim_without_readback',
          'other')
RESOURCE = re.compile(r'[a-z][a-z_]*_\d+\Z')
FIELD_GAPS = ('no validated field-level state', 'completed readback lacks explicit resource, service or event time',
              'readback flag conflicts with row count or HTTP status', 'is missing or not an explicit boolean')


def _cause(assertion, observation, known_systems) -> str:
    text = assertion['explanation']
    if (assertion['system_id'] not in known_systems or not assertion['resource_id']
            or not RESOURCE.fullmatch(assertion['resource_id'])):
        return 'unsupported_source_scope'
    if 'quarantined' in text and 'timestamp' in text:
        return 'timestamp_anomaly'
    if 'mixed identity' in text:
        return 'insufficient_identity_attribution'
    if 'conflicting direct states' in text:
        return 'conflicting_facts'
    if any(gap in text for gap in FIELD_GAPS):
        raw = observation.raw_fields if observation else {}
        if observation and (raw.get('event') in READBACK_EVENTS or observation.source_type in ('json', 'sql')):
            return 'missing_field_level_state'
        return 'operational_claim_without_readback'
    if assertion['classification'] == 'operational_claim' or 'claim' in text or 'documentary' in text:
        return 'operational_claim_without_readback'
    return 'other'


def classify_unknowns(state: dict, policy: dict, ctx) -> list[dict]:
    known_systems = set(ctx.cmap['resource_prefixes']) | {'support_platform'}
    decisions = {(d['system_id'], d['resource_id'], d['topology']): d for d in policy['decisions']}
    rows = []
    for latest in state['latest']:
        if latest['supported']: continue
        key = (latest['system_id'], latest['resource_id'], latest['topology'])
        group = [a for a in state['assertions']
                 if (a['system_id'], a['resource_id'], a['topology']) == key]
        causes = sorted({_cause(a, ctx.by_locator.get((a['evidence_id'], a['locator'])), known_systems)
                         for a in group}, key=CAUSES.index)
        decision = decisions.get(key, {})
        sources = sorted({o.source_type for a in group
                          for o in [ctx.by_locator.get((a['evidence_id'], a['locator']))] if o})
        rows.append({'case_id': state['case_id'], 'system_id': latest['system_id'],
                     'resource_id': latest['resource_id'], 'topology': latest['topology'],
                     'primary_cause': causes[0] if causes else 'other', 'causes': causes,
                     'evidence': sorted({a['evidence_id'] for a in group}), 'source_types': sources,
                     'category': decision.get('category'), 'category_status': decision.get('category_status'),
                     'rule_id': decision.get('rule_id'),
                     'policy_relevant': decision.get('category_status') in ('MAPPED', 'PROCESS')})
    return rows
