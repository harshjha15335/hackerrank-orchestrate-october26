"""Deterministic physical-copy state assertions; no policy or remediation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

from identity.graph import Resolution
from identity.retrieval import Hit, direct_identifiers
from identity.snapshots import SnapshotIndex
from ingest.evidence import Observation, parse_time

DIRECT_FIELDS = ('email', 'phone', 'email_hash', 'full_name', 'display_name',
                 'requester_email', 'requester_phone', 'requester_name',
                 'owner_email', 'owner_phone', 'customer_email')
NULLISH = (None, '', 'null', 'none')
READBACK_EVENTS = {'profile_lookup_completed', 'analytics_profile_read_completed',
                   'support_ticket_read_completed', 'audit_record_read_completed',
                   'connector_config_read_completed', 'restore_policy_read_completed'}
RELIABILITY = {'snapshot': 4, 'readback': 3, 'field_values': 3,
               'operational_claim': 1, 'unknown': 0}


@dataclass(frozen=True)
class StateAssertion:
    case_id: str
    user_id: str | None
    system_id: str | None
    resource_id: str | None
    data_category: str | None
    state: str
    evidence_id: str
    locator: str
    captured_at: str
    event_time: str | None
    record_time: str | None
    topology: str | None
    attribution: str
    classification: str
    supported: bool
    explanation: str
    conflicts: tuple[str, ...] = ()

    def as_dict(self):
        return asdict(self)


def physical_scope(o: Observation) -> str:
    if o.source_type == 'sql':
        # A table is a separate physical copy even inside a shared file.
        return o.locator.split('[', 1)[0]
    return o.topology or 'service'


def system_for(o: Observation) -> str | None:
    if o.system_id: return o.system_id
    if o.source_type == 'sql' and o.locator.startswith('customer_profiles_'):
        return 'account_service'
    return None


def field_values(raw):
    record = raw.get('parsed_record') or raw.get('profile') or raw.get('document') or raw
    return record if isinstance(record, dict) else raw


def _has_direct_values(raw) -> bool:
    values = field_values(raw)
    return any(values.get(k) not in NULLISH for k in DIRECT_FIELDS)


def _state_for_observation(o: Observation):
    raw = o.raw_fields
    values = field_values(raw)
    if o.source_type == 'activity':
        return 'UNKNOWN', 'operational_claim', 'activity result is a claim'
    if o.source_type == 'sql':
        if o.resource_id is None: return 'UNKNOWN', 'unknown', 'scope metadata is not a record'
        if o.data_category == 'connector_subscriptions' or o.resource_id.startswith('data_flow_'):
            if values.get('enabled') in (1, True, '1', 'true'): return 'ACTIVE', 'snapshot', 'enabled connector row'
            if values.get('enabled') in (0, False, '0', 'false'): return 'DISABLED', 'snapshot', 'disabled connector row'
        if o.resource_id.startswith('backup_'):
            if values.get('restore_allowed') in (1, True, '1', 'true'): return 'RESTORE_ENABLED', 'snapshot', 'backup row permits restore'
            if values.get('restore_allowed') in (0, False, '0', 'false'): return 'RESTORE_BLOCKED', 'snapshot', 'backup row blocks restore'
        if o.resource_id.startswith('analytics_') and not _has_direct_values(raw):
            return 'ANONYMIZED', 'snapshot', 'analytics row has no direct identifiers'
        if o.resource_id.startswith(('account_', 'support_')) and not _has_direct_values(raw):
            return 'REDACTED', 'snapshot', 'retained row has no direct identifiers'
        return 'PRESENT', 'snapshot', 'materialized SQL row'
    if o.source_type in ('json', 'log'):
        event = raw.get('event')
        code = raw.get('status_code', raw.get('http_status'))
        rows = raw.get('rows')
        if o.source_type == 'log' and event not in READBACK_EVENTS:
            return 'UNKNOWN', 'operational_claim', 'log event is not a completed readback'
        if code in (404, '404') and rows in (0, '0', None) and (event in READBACK_EVENTS or 'profile_lookups' in o.locator):
            return 'ABSENT', 'readback', 'resource-scoped 404 readback'
        if code in (200, '200') and (rows in (1, '1', None)) and (event in READBACK_EVENTS or 'profile_lookups' in o.locator):
            return 'PRESENT', 'readback', 'resource-scoped 200 readback'
        if event in READBACK_EVENTS and rows in (0, '0'):
            return 'ABSENT', 'readback', 'completed zero-row readback'
        if event in READBACK_EVENTS and rows in (1, '1'):
            return 'PRESENT', 'readback', 'completed one-row readback'
        # "FOUND" and worker results are neither source rows nor verified reads.
        if raw.get('result') is not None:
            return 'UNKNOWN', 'operational_claim', 'result string requires source corroboration'
        if o.source_type == 'json' and o.resource_id:
            if 'enabled' in values:
                return ('ACTIVE' if values['enabled'] in (True, 1, 'true', '1') else 'DISABLED',
                        'field_values', 'connector configuration fields')
            if 'restore_allowed' in values:
                return ('RESTORE_ENABLED' if values['restore_allowed'] in (True, 1, 'true', '1') else 'RESTORE_BLOCKED',
                        'field_values', 'restore policy fields')
            if _has_direct_values(raw): return 'PRESENT', 'field_values', 'observed record contains identifiers'
            if o.resource_id.startswith('analytics_') and values.get('metrics') is not None:
                return 'ANONYMIZED', 'field_values', 'observed analytics fields contain no direct identifiers'
        return 'UNKNOWN', 'operational_claim', 'no validated field-level state'
    return 'UNKNOWN', 'operational_claim', 'documentary or operational statement'


def attribution_for(hit: Hit, resolution: Resolution) -> str:
    if hit.strength != 'mixed_context': return hit.strength
    identities = direct_identifiers(hit.observation.raw_fields)
    allowed = {(v.field, v.normalized) for v in resolution.history}
    allowed.add(('user_id', resolution.user_id))
    # A row containing both user ID and email is safe when each direct key
    # independently belongs to this resolved subject at the audit cutoff.
    return 'direct_verified' if identities and identities <= allowed else 'mixed_context'


def from_hit(hit: Hit, resolution: Resolution, anomalies: set[tuple[str, str]] = frozenset()) -> StateAssertion:
    o = hit.observation
    cutoff = parse_time(resolution.audit_at)
    if parse_time(o.captured_at) > cutoff:
        raise ValueError('post-cutoff observation must never enter reconstruction')
    state, classification, explanation = _state_for_observation(o)
    event = o.event_time or o.record_time
    if (o.evidence_id, o.locator) in anomalies:
        state, classification, explanation = 'UNKNOWN', 'unknown', 'record timestamp exceeds manifest capture; quarantined'
    elif event and (parse_time(event) > cutoff or parse_time(event) > parse_time(o.captured_at)):
        state, classification, explanation = 'UNKNOWN', 'unknown', 'source timestamp is after cutoff or capture; quarantined'
    attribution = attribution_for(hit, resolution)
    if attribution == 'mixed_context':
        state, classification, explanation = 'UNKNOWN', 'unknown', 'mixed identity context is not customer attribution'
    return StateAssertion(resolution.case_id, resolution.user_id, system_for(o), o.resource_id,
                          o.data_category, state, o.evidence_id, o.locator, o.captured_at,
                          o.event_time, o.record_time, physical_scope(o), attribution,
                          classification, state != 'UNKNOWN', explanation)


def _order(a: StateAssertion):
    moment = parse_time(a.captured_at)
    event = parse_time(a.event_time or a.record_time) if (a.event_time or a.record_time) else moment
    return (moment, event, RELIABILITY[a.classification], a.evidence_id, a.locator)


def latest(assertions: Iterable[StateAssertion]) -> list[StateAssertion]:
    groups = defaultdict(list)
    for a in assertions:
        if a.resource_id and a.system_id:
            groups[(a.system_id, a.resource_id, a.topology)].append(a)
    output = []
    for _, group in sorted(groups.items()):
        facts = [a for a in group if a.supported]
        if not facts:
            winner = max(group, key=_order)
            output.append(replace(winner, state='UNKNOWN', supported=False,
                                  explanation='no source-grounded state in scope'))
            continue
        winner = max(facts, key=_order)
        contradictory = tuple(sorted({f'{a.evidence_id}:{a.locator}:{a.state}' for a in facts
                                      if a.state != winner.state}))
        # Equal-time direct facts that disagree are unresolved, never selected by ID.
        tied = [a for a in facts if _order(a)[:2] == _order(winner)[:2] and a.state != winner.state]
        if tied:
            winner = replace(winner, state='UNKNOWN', supported=False,
                             explanation='conflicting direct states at equal observation time')
        output.append(replace(winner, conflicts=contradictory))
    return output


def _authoritative_sql_scope(scope, dataset: Path) -> bool:
    # The explicit point-in-time comparison of complete primary/failover
    # account tables is authoritative for those physical copies only.
    if scope.table not in ('customer_profiles_primary', 'customer_profiles_failover_replica'):
        return False
    text = (dataset / scope.source_path).read_text(encoding='utf-8')
    return ('point-in-time database snapshot' in text and
            'Compare the primary and any replica tables' in text)


def sql_absences(resolution: Resolution, hits: list[Hit], index: SnapshotIndex,
                 dataset: Path) -> list[StateAssertion]:
    if resolution.status != 'resolved': return []
    direct = [h for h in hits if attribution_for(h, resolution) in ('direct', 'direct_verified')
              and h.observation.source_type == 'sql'
              and h.observation.resource_id and system_for(h.observation) == 'account_service'
              and h.observation.locator.startswith('customer_profiles_')]
    output = []
    for ref in direct:
        for table in ('customer_profiles_primary', 'customer_profiles_failover_replica'):
            scope = index.absence_candidate(ref.observation.evidence_id, table,
                                            ref.observation.resource_id, resolution.audit_at,
                                            source_reference=ref.observation)
            if not scope or not _authoritative_sql_scope(scope, dataset): continue
            output.append(StateAssertion(resolution.case_id, resolution.user_id,
                                         'account_service', ref.observation.resource_id,
                                         'customer_profiles', 'ABSENT', scope.evidence_id,
                                         f'{table}:no-row:{ref.observation.resource_id}',
                                         scope.captured_at, None, None, table, 'direct',
                                         'snapshot', True,
                                         'complete point-in-time physical table omits independently attributed resource'))
    return output


def reconstruct(resolution: Resolution, hits: list[Hit], index: SnapshotIndex,
                dataset: Path, anomalies: set[tuple[str, str]] = frozenset()):
    raw = [from_hit(h, resolution, anomalies) for h in hits]
    raw.extend(sql_absences(resolution, hits, index, dataset))
    return {'case_id': resolution.case_id, 'user_id': resolution.user_id,
            'audit_at': resolution.audit_at,
            'assertions': [a.as_dict() for a in sorted(raw, key=lambda a: (_order(a), a.system_id or '', a.resource_id or ''))],
            'latest': [a.as_dict() for a in latest(raw)]}
