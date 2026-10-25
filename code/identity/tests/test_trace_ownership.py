"""F-03 (pre-M9 audit): trace joins resolve ownership through the identity graph.

A trace naming one subject's email and user ID is one identity, not two. A
trace is joinable only when every identifier it names is the resolved
subject's at the cutoff and held by nobody else; a foreign, unknown or shared
identifier keeps it ambiguous, and future lines neither anchor nor contest.
"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from ingest import evidence
from state.engine import attribution_for

CUTOFF = '2026-03-01T00:00:00Z'
META = {'file_id': 'synthetic_file', 'file_path': 'evidence/fixture.log', 'captured_at': '2026-02-01T00:00:00Z'}
HASH_A = 'a' * 64


@pytest.fixture
def graph(tmp_path):
    identities = [
        {'user_id': 'user_101', 'name': 'A', 'email': 'a.new@example.test', 'phone': '+1 555 0100 001',
         'email_hash': HASH_A, 'updated_at': '2026-01-01T00:00:00Z'},
        {'user_id': 'user_102', 'name': 'B', 'email': 'b@example.test', 'phone': '+1 555 0100 002',
         'email_hash': 'b' * 64, 'updated_at': '2026-01-01T00:00:00Z'},
        {'user_id': 'user_103', 'name': 'C', 'email': 'c.now@example.test', 'phone': '',
         'email_hash': 'c' * 64, 'updated_at': '2026-01-01T00:00:00Z'},
    ]
    audit = [
        # A's historical alias, changed before the cutoff.
        {'audit_id': 'audit_1', 'user_id': 'user_101', 'event_time': '2025-06-01T00:00:00Z',
         'field_name': 'email', 'old_value': 'a.old@example.test', 'new_value': 'a.new@example.test'},
        # An address that moved from C to... C had it, B later took it: shared ever.
        {'audit_id': 'audit_2', 'user_id': 'user_103', 'event_time': '2025-07-01T00:00:00Z',
         'field_name': 'email', 'old_value': 'shared@example.test', 'new_value': 'c.now@example.test'},
        {'audit_id': 'audit_3', 'user_id': 'user_101', 'event_time': '2025-08-01T00:00:00Z',
         'field_name': 'phone', 'old_value': '+1 555 0100 009', 'new_value': '+1 555 0100 001'},
        {'audit_id': 'audit_4', 'user_id': 'user_101', 'event_time': '2025-09-01T00:00:00Z',
         'field_name': 'email', 'old_value': 'a.mid@example.test', 'new_value': 'a.new@example.test'},
        {'audit_id': 'audit_5', 'user_id': 'user_102', 'event_time': '2025-09-01T00:00:00Z',
         'field_name': 'email', 'old_value': 'shared@example.test', 'new_value': 'b@example.test'},
    ]
    for name, rows in (('user_identities.csv', identities), ('user_audit_log.csv', audit)):
        with (tmp_path / name).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return IdentityGraph(tmp_path)


def resolve(graph, email='a.new@example.test', cutoff=CUTOFF):
    return graph.resolve({'case_id': 'synthetic', 'email': email, 'audit_at': cutoff})


def line(n, fields, trace='tr-1', captured=None, event_time=None):
    meta = dict(META, captured_at=captured) if captured else META
    return evidence.make(meta, f'line:{n}', dict(fields, trace_id=trace), 'log', event_time=event_time)


def downstream(n=3, resource='analytics_501'):
    return line(n, {'event': 'analytics_profile_read', 'resource_id': resource, 'service': 'analytics_platform'})


def joined(index, resolution):
    return {h.observation.locator: h.strength for h in index.find(resolution)}


def test_graph_owners_cover_snapshot_and_history(graph):
    assert graph.owners('email', 'a.old@example.test') == {'user_101'}
    assert graph.owners('email', 'shared@example.test') == {'user_102', 'user_103'}
    assert graph.owners('user_id', 'user_102') == {'user_102'}
    assert graph.owners('email', 'nobody@example.test') == frozenset()


def test_email_and_user_id_of_one_subject_join_the_trace(graph):
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), line(2, {'user_id': 'user_101'}), downstream()]
    res = resolve(graph)
    assert joined(EvidenceIndex(obs, graph=graph), res) == {'line:1': 'direct', 'line:2': 'direct',
                                                          'line:3': 'correlated'}
    # Without the identity graph the M2 rule stays conservative (two customer identifiers).
    assert 'line:3' not in joined(EvidenceIndex(obs), res)


def test_same_record_email_and_user_id_is_verified_not_mixed(graph):
    obs = [line(1, {'email': 'a.new@example.test', 'user_id': 'user_101', 'resource_id': 'account_1'})]
    res = resolve(graph)
    [hit] = EvidenceIndex(obs, graph=graph).find(res)
    assert hit.strength == 'mixed_context' and not hit.owner_conflict
    assert attribution_for(hit, res) == 'direct_verified'


def test_historical_alias_joins(graph):
    obs = [line(1, {'lookup_key': 'a.old@example.test'}), line(2, {'user_id': 'user_101'}), downstream()]
    assert joined(EvidenceIndex(obs, graph=graph), resolve(graph))['line:3'] == 'correlated'


def test_cross_person_trace_is_rejected(graph):
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), line(2, {'user_id': 'user_102'}), downstream()]
    hits = joined(EvidenceIndex(obs, graph=graph), resolve(graph))
    assert 'line:3' not in hits and 'line:2' not in hits


def test_foreign_customer_does_not_inherit_subjects_resource(graph):
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), line(2, {'user_id': 'user_101'}), downstream()]
    other = resolve(graph, email='b@example.test')
    assert joined(EvidenceIndex(obs, graph=graph), other) == {}


def test_same_record_with_two_subjects_stays_mixed(graph):
    obs = [line(1, {'email': 'a.new@example.test', 'user_id': 'user_102', 'resource_id': 'account_1'})]
    res = resolve(graph)
    [hit] = EvidenceIndex(obs, graph=graph).find(res)
    assert hit.owner_conflict and attribution_for(hit, res) == 'mixed_context'


def test_unknown_identifier_keeps_trace_ambiguous(graph):
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), line(2, {'customer_email': 'stranger@example.test'}),
           downstream()]
    assert 'line:3' not in joined(EvidenceIndex(obs, graph=graph), resolve(graph))


def test_identifier_held_by_two_people_is_not_ownership(graph):
    # shared@ was held by both B and C; it cannot anchor C's trace exclusively.
    obs = [line(1, {'lookup_key': 'shared@example.test'}), downstream(2)]
    res = resolve(graph, email='c.now@example.test')
    assert res.user_id == 'user_103'
    hits = EvidenceIndex(obs, graph=graph).find(res)
    assert 'line:2' not in {h.observation.locator for h in hits}


def test_foreign_phone_in_trace_rejects_join(graph):
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), line(2, {'owner_phone': '+1 555 0100 002'}), downstream()]
    assert 'line:3' not in joined(EvidenceIndex(obs, graph=graph), resolve(graph))


def test_identifier_free_downstream_needs_an_anchor(graph):
    obs = [downstream(1), line(2, {'event': 'connection_acquired'})]
    assert joined(EvidenceIndex(obs, graph=graph), resolve(graph)) == {}


def test_trace_id_alone_is_not_ownership_across_files(graph):
    anchor = line(1, {'lookup_key': 'a.new@example.test'})
    other_file = evidence.make(dict(META, file_id='other_file'), 'line:9',
                               {'trace_id': 'tr-1', 'resource_id': 'analytics_777'}, 'log')
    assert 'line:9' not in joined(EvidenceIndex([anchor, other_file], graph=graph), resolve(graph))


def test_future_line_neither_anchors_nor_contests(graph):
    future_foreign = line(2, {'user_id': 'user_102'}, captured='2026-02-01T00:00:00Z', event_time='2026-04-01T00:00:00Z')
    obs = [line(1, {'lookup_key': 'a.new@example.test'}), future_foreign, downstream()]
    assert joined(EvidenceIndex(obs, graph=graph), resolve(graph))['line:3'] == 'correlated'
    future_anchor = line(1, {'lookup_key': 'a.new@example.test'}, event_time='2026-04-01T00:00:00Z')
    assert 'line:3' not in joined(EvidenceIndex([future_anchor, downstream()], graph=graph), resolve(graph))


def test_alias_acquired_after_cutoff_is_not_the_subjects(graph):
    # Before audit_1 A was a.old@ only; a.new@ (gained later) cannot anchor A's trace.
    early_cutoff, captured = '2025-05-01T00:00:00Z', '2025-04-01T00:00:00Z'
    early = resolve(graph, email='a.old@example.test', cutoff=early_cutoff)
    assert early.user_id == 'user_101'
    obs = [line(1, {'lookup_key': 'a.new@example.test'}, captured=captured),
           line(2, {'lookup_key': 'a.old@example.test'}, captured=captured),
           line(3, {'event': 'analytics_profile_read', 'resource_id': 'analytics_501'}, captured=captured)]
    assert 'line:3' not in joined(EvidenceIndex(obs, graph=graph), early)
    assert joined(EvidenceIndex(obs[1:], graph=graph), early)['line:3'] == 'correlated'
