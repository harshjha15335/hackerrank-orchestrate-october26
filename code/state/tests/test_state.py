import json
import socket
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import Resolution
from identity.retrieval import Hit
from ingest.evidence import Observation
from state.engine import from_hit, latest, reconstruct, sql_absences
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


def test_full_518_cutoff_determinism_and_anomaly_quarantine():
    a = run_all(ROOT / 'dataset', cache=Path('/tmp/m4-ingest-cache'))
    b = run_all(ROOT / 'dataset', cache=Path('/tmp/m4-ingest-cache'))
    assert a == b and a['case_count'] == 518 and a['cutoff_violations'] == 0
    assert len(a['timestamp_anomalies']) == 2
    assert all(d['reason'] == 'record_time_after_manifest_capture' for d in a['timestamp_anomalies'])
