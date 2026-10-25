import json
import socket
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import Resolution
from identity.retrieval import Hit, direct_identifiers
from ingest.evidence import Observation
from state.engine import from_hit, latest, parse_source_bool, sql_absences
from state.main import build, run_all, run_case

ROOT = Path(__file__).resolve().parents[3]
T = '2026-09-02T23:00:00Z'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network')))


def resolution(cutoff=T):
    return Resolution('synthetic_case', cutoff, 'user_1', ('user_1',), 'resolved',
                      {'email': 'u@example.com'}, ())


def observation(kind='sql', *, state=None, capture=T, event=None, record=None,
                raw=None, resource='account_1', topology='primary', locator='customer_profiles_primary[1]'):
    raw = raw if raw is not None else {'resource_id': resource, 'email': 'u@example.com'}
    return Observation('synthetic_evidence', 'evidence/synthetic.sql', locator, capture,
                       'account_service', resource, 'customer_profiles', state,
                       (('u@example.com', 'u@example.com'),), raw, kind, topology,
                       record, event, 'synthetic_source')


def assertion(**kwargs):
    o = observation(**kwargs)
    return from_hit(Hit(o, (('email', 'u@example.com'),), 'direct'), resolution())


def test_sql_row_is_present_and_claimed_success_is_not_absence():
    assert assertion().state == 'PRESENT'
    o = observation('activity', raw={'reported_result': 'SUCCESS', 'resource_id': 'account_1'})
    a = from_hit(Hit(o, (), 'direct'), resolution())
    assert a.state == 'UNKNOWN' and not a.supported and a.classification == 'operational_claim'


def test_found_string_is_not_current_presence():
    a = assertion(kind='json', raw={'resource_id': 'account_1', 'result': 'FOUND',
                                    'subject_reference': 'u@example.com'})
    assert a.state == 'UNKNOWN' and not a.supported


def test_verified_http_readbacks_and_null_identifiers():
    for code, rows, expected in [(200, 1, 'PRESENT'), (404, 0, 'ABSENT')]:
        a = assertion(kind='log', event=T, locator='line:1',
                      raw={'event': 'profile_lookup_completed', 'http_status': str(code),
                           'rows': str(rows), 'resource_id': 'account_1'})
        assert a.state == expected and a.supported
    a = assertion(raw={'resource_id': 'account_1', 'email': None, 'phone': None,
                       'full_name': None})
    assert a.state == 'REDACTED'


def test_restore_and_connector_flags_preserve_physical_state():
    for resource, raw, state in [('backup_1', {'restore_allowed': 1}, 'RESTORE_ENABLED'),
                                 ('backup_1', {'restore_allowed': 0}, 'RESTORE_BLOCKED'),
                                 ('data_flow_1', {'enabled': 1}, 'ACTIVE'),
                                 ('data_flow_1', {'enabled': 0}, 'DISABLED')]:
        a = assertion(resource=resource, raw={'resource_id': resource, **raw})
        assert a.state == state


@pytest.mark.parametrize('raw,expected', [(True, True), (False, False), (1, True), (0, False),
                                         ('true', True), ('FALSE', False), (' 1 ', True), ('0', False),
                                         (None, None), ('null', None), ('yes', None), ('', None),
                                         (2, None), (1.0, None), ({'value': True}, None)])
def test_strict_source_boolean(raw, expected):
    assert parse_source_bool(raw) is expected


@pytest.mark.parametrize('kind,resource,flag', [('sql', 'data_flow_1', 'enabled'),
                                               ('json', 'data_flow_1', 'enabled'),
                                               ('sql', 'backup_1', 'restore_allowed'),
                                               ('json', 'backup_1', 'restore_allowed')])
@pytest.mark.parametrize('value', [None, 'null', 'maybe', 2, 1.0])
def test_invalid_or_missing_flags_never_become_safe_states(kind, resource, flag, value):
    for raw in ({'resource_id': resource, flag: value}, {'resource_id': resource}):
        a = assertion(kind=kind, resource=resource, raw=raw)
        assert a.state == 'UNKNOWN' and not a.supported


def completed_log(event, resource, flag, value, *, capture=T, when='2026-09-02T22:00:00Z', **extra):
    service = 'integration_service' if event.startswith('connector') else 'backup_service'
    raw = {'event': event, 'service': service, 'resource_id': resource, flag: value, **extra}
    o = replace(observation('log', raw=raw, resource=resource, capture=capture, event=when,
                            locator='line:17'), system_id=service)
    return from_hit(Hit(o, (('user_id', 'user_1'),), 'direct'), resolution())


@pytest.mark.parametrize('event,resource,flag,value,expected', [
    ('connector_config_read_completed', 'data_flow_1', 'enabled', 'true', 'ACTIVE'),
    ('connector_config_read_completed', 'data_flow_1', 'enabled', 'false', 'DISABLED'),
    ('restore_policy_read_completed', 'backup_1', 'restore_allowed', 'true', 'RESTORE_ENABLED'),
    ('restore_policy_read_completed', 'backup_1', 'restore_allowed', 'false', 'RESTORE_BLOCKED'),
])
def test_completed_flag_readbacks_are_scoped_and_preserve_provenance(event, resource, flag, value, expected):
    a = completed_log(event, resource, flag, value, rows='1', http_status='200')
    assert a.state == expected and a.supported and a.classification == 'readback'
    assert (a.resource_id, a.evidence_id, a.locator) == (resource, 'synthetic_evidence', 'line:17')


@pytest.mark.parametrize('value', [None, 'null', 'maybe', '', 2])
def test_completed_log_invalid_flags_remain_unknown_even_with_rows(value):
    a = completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', value,
                      rows='1', http_status='200')
    assert a.state == 'UNKNOWN' and not a.supported


def test_uncompleted_claim_and_unscoped_or_conflicting_readbacks():
    o = replace(observation('log', raw={'event': 'connector_config_read_started',
                                        'service': 'integration_service', 'resource_id': 'data_flow_1',
                                        'enabled': 'false'}, resource='data_flow_1', event=T),
                system_id='integration_service')
    assert from_hit(Hit(o, (), 'direct'), resolution()).state == 'UNKNOWN'
    assert completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'false',
                         rows='0').state == 'UNKNOWN'
    assert completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'false',
                         http_status='404').state == 'UNKNOWN'
    assert completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'false',
                         rows=True).state == 'UNKNOWN'
    assert completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'false',
                         status_code='404').state == 'UNKNOWN'
    missing = replace(observation('log', raw={'event': 'connector_config_read_completed',
                                               'service': 'integration_service', 'enabled': 'false'},
                                  event=T), system_id='integration_service')
    assert from_hit(Hit(missing, (), 'direct'), resolution()).state == 'UNKNOWN'
    wrong = replace(observation('log', raw={'event': 'connector_config_read_completed',
                                            'service': 'backup_service', 'resource_id': 'data_flow_1',
                                            'enabled': 'false'}, resource='data_flow_1', event=T),
                    system_id='backup_service')
    assert from_hit(Hit(wrong, (), 'direct'), resolution()).state == 'UNKNOWN'


def test_flag_readback_timeline_conflict_and_cutoff():
    old = completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'true',
                        capture='2026-09-02T21:00:00Z', when='2026-09-02T20:50:00Z')
    new = completed_log('connector_config_read_completed', 'data_flow_1', 'enabled', 'false')
    result = latest([old, new])[0]
    assert result.state == 'DISABLED' and result.conflicts
    assert latest([new, old])[0] == result
    tied = replace(new, state='ACTIVE', locator='line:18')
    assert latest([new, tied])[0].state == 'UNKNOWN'
    boundary = completed_log('restore_policy_read_completed', 'backup_1', 'restore_allowed', 'false',
                             capture='2026-09-03T00:00:00+01:00', when='2026-09-02T22:55:00Z')
    assert boundary.state == 'RESTORE_BLOCKED'
    with pytest.raises(ValueError):
        completed_log('restore_policy_read_completed', 'backup_1', 'restore_allowed', 'false',
                      capture='2026-09-03T00:00:01+01:00')


def test_timeline_resync_and_verified_deletion():
    old = assertion(capture='2026-09-02T21:00:00Z', kind='log',
                    event='2026-09-02T20:00:00Z', locator='line:1',
                    raw={'event': 'profile_lookup_completed', 'http_status': '404', 'rows': '0'})
    new = assertion(capture='2026-09-02T22:00:00Z', kind='log',
                    event='2026-09-02T21:30:00Z', locator='line:2',
                    raw={'event': 'profile_lookup_completed', 'http_status': '200', 'rows': '1'})
    assert latest([old, new])[0].state == 'PRESENT'
    newer = assertion(capture=T, kind='log', event='2026-09-02T22:30:00Z', locator='line:3',
                      raw={'event': 'profile_lookup_completed', 'http_status': '404', 'rows': '0'})
    assert latest([new, newer])[0].state == 'ABSENT'
    assert latest([new, newer])[0].conflicts


def test_equal_time_conflict_is_explicit_unknown():
    a = assertion()
    b = replace(a, state='ABSENT', locator='customer_profiles_primary[2]')
    result = latest([a, b])[0]
    assert result.state == 'UNKNOWN' and result.conflicts
    assert latest([b, a]) == latest([a, b])


def test_cutoff_and_timezone_aware_event_quarantine():
    post = observation(capture='2026-09-03T00:00:00+01:00')  # same instant as cutoff
    assert from_hit(Hit(post, (), 'direct'), resolution()).supported
    with pytest.raises(ValueError):
        from_hit(Hit(observation(capture='2026-09-03T01:00:00+01:00'), (), 'direct'), resolution())
    suspect = assertion(record='2026-09-03T00:01:00Z')
    assert suspect.state == 'UNKNOWN' and not suspect.supported


@pytest.fixture(scope='module')
def real():
    return build(ROOT / 'dataset', Path('/tmp/m4-ingest-cache'))


def drift_fixture(real):
    graph, evidence, scopes, _ = real
    by_file = {}
    for o in evidence.observations:
        if o.source_type == 'sql' and o.locator.startswith('customer_profiles_') and o.resource_id:
            by_file.setdefault(o.evidence_id, {}).setdefault(o.locator.split('[')[0], set()).add(o.resource_id)
    for file_id, tables in sorted(by_file.items()):
        replica = tables.get('customer_profiles_failover_replica', set())
        primary = tables.get('customer_profiles_primary', set())
        for resource in sorted(replica - primary):
            for case in graph.requests(True):
                resolved = graph.resolve(case)
                if any(h.observation.evidence_id == file_id and h.observation.resource_id == resource
                       for h in evidence.find(resolved)):
                    return case, file_id, resource
    raise AssertionError('no source-grounded primary/replica drift fixture')


def test_real_primary_failover_drift_and_attribution(real):
    graph, evidence, scopes, discrepancies = real
    case, _, resource = drift_fixture(real)
    result = run_case(case, graph, evidence, scopes, ROOT / 'dataset', set())
    copies = [a for a in result['latest'] if a['resource_id'] == resource]
    assert {a['topology']: a['state'] for a in copies} == {
        'customer_profiles_failover_replica': 'PRESENT', 'customer_profiles_primary': 'ABSENT'}
    assert all(a['attribution'] in ('direct', 'direct_verified') for a in copies)


def test_negative_sql_scope_needs_independent_reference(real):
    graph, evidence, scopes, _ = real
    case, file_id, resource = drift_fixture(real)
    resolved = graph.resolve(case)
    assert sql_absences(resolved, [], scopes, ROOT / 'dataset') == []
    assert scopes.absence_candidate(file_id, 'customer_profiles_primary',
                                    resource, resolved.audit_at) is None


def test_participant_completed_connector_and_restore_log_structures(real):
    _, evidence, _, _ = real
    seen = set()
    for o in evidence.observations:
        if o.source_type != 'log' or o.raw_fields.get('event') not in (
                'connector_config_read_completed', 'restore_policy_read_completed'):
            continue
        event = o.raw_fields['event']
        flag = 'enabled' if event.startswith('connector') else 'restore_allowed'
        value = parse_source_bool(o.raw_fields.get(flag))
        if value is None: continue
        # This checks flag parsing only: the line's customer identifiers belong to
        # a real dataset user, not the synthetic subject, so they are dropped here
        # (attribution itself is covered by identity/tests/test_cross_customer.py).
        o = replace(o, raw_fields={k: v for k, v in o.raw_fields.items() if not direct_identifiers({k: v})})
        a = from_hit(Hit(o, (), 'direct'), resolution(o.captured_at))
        expected = (('ACTIVE' if value else 'DISABLED') if flag == 'enabled' else
                    ('RESTORE_ENABLED' if value else 'RESTORE_BLOCKED'))
        assert a.state == expected and a.supported
        assert (a.resource_id, a.evidence_id, a.locator) == (o.resource_id, o.evidence_id, o.locator)
        seen.add((flag, value))
    assert {('enabled', True), ('enabled', False), ('restore_allowed', True),
            ('restore_allowed', False)} <= seen


def test_full_518_cutoff_determinism_and_anomaly_quarantine():
    a = run_all(ROOT / 'dataset', cache=Path('/tmp/m4-ingest-cache'))
    b = run_all(ROOT / 'dataset', cache=Path('/tmp/m4-ingest-cache'))
    assert a == b and a['case_count'] == 518 and a['cutoff_violations'] == 0
    assert len(a['timestamp_anomalies']) == 2
    assert all(d['reason'] == 'record_time_after_manifest_capture' for d in a['timestamp_anomalies'])


def field_record(kind, system, resource, raw, event=None):
    o = Observation('synthetic_evidence', 'evidence/synthetic', 'line:1' if kind == 'log' else '$.records[0]', T,
                    system, resource, None, None, (('u@example.com', 'u@example.com'),),
                    {'resource_id': resource, **raw}, kind, None, None, event)
    return from_hit(Hit(o, (('email', 'u@example.com'),), 'direct'), resolution())


def test_completed_readback_with_returned_fields():
    # M5 review: completed resource-scoped reads that return field values, with no row/HTTP keys.
    base = {'event': 'support_ticket_read_completed', 'service': 'support_platform', 'trace_id': 'rb-1'}
    nulls = field_record('log', 'support_platform', 'support_1',
                         {**base, 'customer_reference': 'user_1', 'requester_email': 'null', 'requester_phone': 'null'}, T)
    assert (nulls.state, nulls.classification) == ('REDACTED', 'readback')
    exposed = field_record('log', 'support_platform', 'support_1',
                           {**base, 'requester_email': 'u@example.com'}, T)
    assert exposed.state == 'PRESENT' and exposed.supported
    analytics = field_record('log', 'analytics_platform', 'analytics_1',
                             {'event': 'analytics_profile_read_completed', 'service': 'analytics_platform',
                              'audience_cohort': 'x', 'email': 'null', 'phone': 'null'}, T)
    assert analytics.state == 'ANONYMIZED'


@pytest.mark.parametrize('raw,event', [
    ({'event': 'support_ticket_read_completed', 'service': 'support_platform'}, T),           # envelope only
    ({'event': 'support_ticket_read_completed', 'service': 'other_service',
      'requester_email': 'u@example.com'}, T),                                                  # service mismatch
    ({'event': 'support_ticket_read_completed', 'service': 'support_platform',
      'requester_email': 'u@example.com'}, None),                                               # no event time
    ({'event': 'support_ticket_read_started', 'service': 'support_platform',
      'lookup_key': 'u@example.com'}, T),                                                      # not completed
    ({'event': 'support_ticket_read_completed', 'service': 'support_platform',
      'requester_email': 'null', 'requester_name': 'null'}, T),                                 # only nulls
])
def test_incomplete_or_unscoped_readbacks_stay_unknown(raw, event):
    a = field_record('log', 'support_platform', 'support_1', raw, event)
    assert a.state == 'UNKNOWN' and not a.supported


def test_json_records_with_own_fields():
    audit = field_record('json', 'security_service', 'audit_record_1',
                         {'subject_reference': 'user_1', 'event_code': 'X', 'retention_until': '2030-01-01T00:00:00Z'})
    assert (audit.state, audit.classification) == ('PRESENT', 'field_values')
    redacted = field_record('json', 'support_platform', 'support_1',
                            {'customer_reference': 'user_1', 'message_excerpt': 'x', 'requester_email': None})
    assert redacted.state == 'REDACTED'
    for raw in ({'subject_reference': 'u@example.com', 'result': 'FOUND', 'record_type': 'X'},   # claim
                {'observed_at': T},                                                               # envelope
                {'email': None, 'phone': None, 'customer_reference': None}):                     # analytics, no content
        a = field_record('json', 'analytics_platform', 'analytics_1', raw)
        assert a.state == 'UNKNOWN', raw
