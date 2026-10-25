"""Deterministic physical-copy state assertions; no policy or remediation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from identity.graph import Resolution, norm
from identity.retrieval import Hit, direct_identifiers
from identity.snapshots import SnapshotIndex
from ingest.evidence import TABLE_SYSTEM, Observation, parse_time

DIRECT_FIELDS = ('email', 'phone', 'email_hash', 'full_name', 'display_name',
                 'requester_email', 'requester_phone', 'requester_name',
                 'owner_email', 'owner_phone', 'customer_email')
NULLISH = (None, '', 'null', 'none')
READBACK_EVENTS = {'profile_lookup_completed', 'analytics_profile_read_completed',
                   'support_ticket_read_completed', 'audit_record_read_completed',
                   'connector_config_read_completed', 'restore_policy_read_completed'}
RELIABILITY = {'snapshot': 4, 'readback': 3, 'field_values': 3, 'visual_field_values': 2,
               'operational_claim': 1, 'unknown': 0}
# M8: prefixes whose question is whether identifiers remain; a screenshot that
# shows none cannot prove redaction or anonymization (the UI may omit fields).
VISUAL_IDENTITY_QUESTION = ('account_', 'support_', 'analytics_')
VISUAL_META = {'resource_id', 'visual', 'expires_at'}


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


# Owning systems named by M1's table map; a file whose manifest origin is one of
# them was exported by that system (M7: closes system-less record gaps).
KNOWN_SYSTEMS = frozenset(TABLE_SYSTEM.values())
# Snapshot tables whose name differs from M1's table map only by the
# "customer_" prefix (customer_search_primary_*.sql uses search_documents_*).
TABLE_ALIASES = {'search_documents': 'search_service'}


def system_for(o: Observation) -> str | None:
    if o.system_id: return o.system_id
    if o.source_type == 'sql' and o.locator.startswith('customer_profiles_'):
        return 'account_service'
    if o.source_type == 'sql':
        table = o.locator.split('[', 1)[0]
        for prefix, system in TABLE_ALIASES.items():
            if table == prefix or table.startswith(prefix + '_'):
                return system
    if o.source_type not in ('activity', 'audit') and o.source_origin in KNOWN_SYSTEMS:
        return o.source_origin
    return None


def field_values(raw):
    record = raw.get('parsed_record') or raw.get('profile') or raw.get('document') or raw
    return record if isinstance(record, dict) else raw


def _has_direct_values(raw) -> bool:
    values = field_values(raw)
    return any(values.get(k) not in NULLISH for k in DIRECT_FIELDS)


def parse_source_bool(value) -> bool | None:
    """Recognize only source booleans, SQLite 0/1 and log/SQL text forms."""
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().casefold()
        if word in ('true', '1'):
            return True
        if word in ('false', '0'):
            return False
    return None


def flag_state(raw, flag: str, true_state: str, false_state: str, classification: str):
    value = parse_source_bool(raw.get(flag))
    if value is None:
        return 'UNKNOWN', 'unknown', f'{flag} is missing or not an explicit boolean'
    return (true_state if value else false_state), classification, f'validated {flag}={str(value).lower()}'


def completed_flag_readback(o: Observation, event: str):
    """Accept flag evidence only from a completed, resource-scoped source read."""
    raw = o.raw_fields
    expected = {'connector_config_read_completed': ('integration_service', 'data_flow_', 'enabled', 'ACTIVE', 'DISABLED'),
                'restore_policy_read_completed': ('backup_service', 'backup_', 'restore_allowed',
                                                  'RESTORE_ENABLED', 'RESTORE_BLOCKED')}
    system, prefix, flag, true_state, false_state = expected[event]
    if (not o.resource_id or not o.resource_id.startswith(prefix) or
            raw.get('resource_id') != o.resource_id or o.system_id != system or
            raw.get('service') != system or not o.event_time):
        return 'UNKNOWN', 'unknown', 'completed readback lacks explicit resource, service or event time'
    if ('rows' in raw and (type(raw['rows']) not in (int, str) or str(raw['rows']).strip() != '1')):
        return 'UNKNOWN', 'unknown', 'readback flag conflicts with row count or HTTP status'
    if any(key in raw and (type(raw[key]) not in (int, str) or str(raw[key]).strip() != '200')
           for key in ('http_status', 'status_code')):
        return 'UNKNOWN', 'unknown', 'readback flag conflicts with row count or HTTP status'
    return flag_state(raw, flag, true_state, false_state, 'readback')


# Envelope/transport keys that describe how a record was read, not the record.
ENVELOPE = {'resource_id', 'observed_at', 'recorded_at', 'updated_at', 'event', 'event_time', 'level',
            'service', 'trace_id', 'instance', 'pod', 'region', 'text', 'duration_ms', 'latency_ms',
            'attempt', 'seq'}
CLAIM_KEYS = {'result', 'status_code', 'http_status', 'rows', 'reported_result'}
CONTENT = ('metrics', 'audience_cohort')


def _record_state(o: Observation, values, classification):
    """State of a record whose own field values were observed (no claim/status keys).

    Only field-bearing records qualify: an envelope with no record fields, a
    result string or a row/HTTP status is not a materialized record.
    """
    fields = {k: v for k, v in values.items() if k not in ENVELOPE}
    if not fields or CLAIM_KEYS & set(values) or not any(v not in NULLISH for v in fields.values()):
        return None
    if _has_direct_values(values):
        return 'PRESENT', classification, 'observed record fields contain identifiers'
    if o.resource_id.startswith('analytics_'):
        if any(values.get(k) not in NULLISH for k in CONTENT):
            return 'ANONYMIZED', classification, 'observed analytics fields contain no direct identifiers'
        return None
    if o.resource_id.startswith(('account_', 'support_')):
        return 'REDACTED', classification, 'observed retained record has no direct identifiers'
    return 'PRESENT', classification, 'observed record fields'


def _state_for_observation(o: Observation):
    raw = o.raw_fields
    values = field_values(raw)
    if o.source_type == 'activity':
        return 'UNKNOWN', 'operational_claim', 'activity result is a claim'
    if o.source_type == 'sql':
        if o.resource_id is None: return 'UNKNOWN', 'unknown', 'scope metadata is not a record'
        if o.data_category == 'connector_subscriptions' or o.resource_id.startswith('data_flow_'):
            return flag_state(values, 'enabled', 'ACTIVE', 'DISABLED', 'snapshot')
        if o.resource_id.startswith('backup_'):
            return flag_state(values, 'restore_allowed', 'RESTORE_ENABLED', 'RESTORE_BLOCKED', 'snapshot')
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
        if o.source_type == 'log' and event in ('connector_config_read_completed', 'restore_policy_read_completed'):
            return completed_flag_readback(o, event)
        if code in (404, '404') and rows in (0, '0', None) and (event in READBACK_EVENTS or 'profile_lookups' in o.locator):
            return 'ABSENT', 'readback', 'resource-scoped 404 readback'
        if code in (200, '200') and (rows in (1, '1', None)) and (event in READBACK_EVENTS or 'profile_lookups' in o.locator):
            return 'PRESENT', 'readback', 'resource-scoped 200 readback'
        if event in READBACK_EVENTS and rows in (0, '0'):
            return 'ABSENT', 'readback', 'completed zero-row readback'
        if event in READBACK_EVENTS and rows in (1, '1'):
            return 'PRESENT', 'readback', 'completed one-row readback'
        # A completed, resource-scoped read that returned the record's fields
        # (no row count or HTTP status) is a readback of those fields.
        if (o.source_type == 'log' and event in READBACK_EVENTS and o.resource_id and
                raw.get('resource_id') == o.resource_id and raw.get('service') == o.system_id and
                o.event_time and code is None and rows is None):
            found = _record_state(o, raw, 'readback')
            if found: return found
        # "FOUND" and worker results are neither source rows nor verified reads.
        if raw.get('result') is not None:
            return 'UNKNOWN', 'operational_claim', 'result string requires source corroboration'
        if o.source_type == 'json' and o.resource_id:
            if o.resource_id.startswith('data_flow_'):
                return flag_state(values, 'enabled', 'ACTIVE', 'DISABLED', 'field_values')
            if o.resource_id.startswith('backup_'):
                return flag_state(values, 'restore_allowed', 'RESTORE_ENABLED', 'RESTORE_BLOCKED', 'field_values')
            if _has_direct_values(raw): return 'PRESENT', 'field_values', 'observed record contains identifiers'
            if o.resource_id.startswith('analytics_') and values.get('metrics') is not None:
                return 'ANONYMIZED', 'field_values', 'observed analytics fields contain no direct identifiers'
            found = _record_state(o, values, 'field_values')
            if found: return found
        return 'UNKNOWN', 'operational_claim', 'no validated field-level state'
    if o.source_type == 'image':
        return _visual_state(o)
    return 'UNKNOWN', 'operational_claim', 'documentary or operational statement'


def _visual_state(o: Observation):
    """M8 screenshot record: positive presence only, never a favourable state."""
    if not o.resource_id:
        return 'UNKNOWN', 'unknown', 'screenshot record has no visible resource ID'
    if o.resource_id.startswith(('data_flow_', 'backup_')):
        # Process state needs an explicit control; M6 reads visual risk separately.
        return 'UNKNOWN', 'unknown', 'screenshot shows no explicit enabled/restore_allowed control'
    fields = {k: v for k, v in o.raw_fields.items() if k not in VISUAL_META}
    if _has_direct_values(fields):
        return 'PRESENT', 'visual_field_values', 'screenshot shows the record with direct identifier values'
    if any(v not in NULLISH for v in fields.values()) and not o.resource_id.startswith(VISUAL_IDENTITY_QUESTION):
        return 'PRESENT', 'visual_field_values', 'screenshot lists the record with its fields'
    return 'UNKNOWN', 'unknown', 'a screenshot without identifiers proves neither redaction nor anonymization'


def attribution_for(hit: Hit, resolution: Resolution) -> str:
    """Attribution strength of one hit; 'mixed_context' never supports a state.

    Every customer identifier on the record (email, user_id, phone, email hash,
    at any depth) must be one of this subject's identifiers. A matching email
    never outweighs another customer's phone or user ID, and an identifier the
    identity graph ties to anyone else, or to nobody, is an owner conflict.
    """
    identities = direct_identifiers(hit.observation.raw_fields)
    allowed = {(v.field, v.normalized) for v in resolution.history}
    allowed.add(('user_id', resolution.user_id))
    for name, value in (resolution.current_at_cutoff or {}).items():
        if name in ('email', 'phone', 'email_hash') and value:
            allowed.add((name, norm(name, value)))
    if hit.owner_conflict or not identities <= allowed:
        return 'mixed_context'
    # A row containing both user ID and email is safe when each direct key
    # independently belongs to this resolved subject at the audit cutoff.
    if hit.strength != 'mixed_context': return hit.strength
    return 'direct_verified' if identities else 'mixed_context'


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
    expiry = o.raw_fields.get('expires_at') if o.source_type == 'image' else None
    if state == 'PRESENT' and isinstance(expiry, str) and parse_time(expiry) <= cutoff:
        # A visible expiry is a schedule, not proof of deletion; the screenshot
        # cannot show the record after it, so presence is not carried past it.
        state, classification, explanation = 'UNKNOWN', 'unknown', 'visible expiry precedes audit_at; state after expiry not shown'
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


def table_system(table: str) -> str | None:
    """Owning system of a snapshot table copy (an absence names no row to read it from)."""
    if table.startswith('customer_profiles_'): return 'account_service'
    for prefix, system in TABLE_ALIASES.items():
        if table == prefix or table.startswith(prefix + '_'): return system
    return TABLE_SYSTEM.get(table)


def authoritative_sql_scope(scope, dataset: Path) -> bool:
    return _authoritative_sql_scope(scope, dataset)


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
                dataset: Path, anomalies: set[tuple[str, str]] = frozenset(), extra=()):
    raw = [from_hit(h, resolution, anomalies) for h in hits]
    raw.extend(sql_absences(resolution, hits, index, dataset))
    raw.extend(extra)
    return {'case_id': resolution.case_id, 'user_id': resolution.user_id,
            'audit_at': resolution.audit_at,
            'assertions': [a.as_dict() for a in sorted(raw, key=lambda a: (_order(a), a.system_id or '', a.resource_id or ''))],
            'latest': [a.as_dict() for a in latest(raw)]}
