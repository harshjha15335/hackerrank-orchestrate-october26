"""Codex re-test: a record naming the subject and another customer never
supports a state for the subject.

M4 attribution requires every customer identifier on a record (email,
user_id, phone, email hash, at any depth) to be the resolved subject's and
nobody else's. A correct email never outweighs another customer's phone; an
unknown or shared identifier is an owner conflict; staff/actor fields (a
support agent's contact details) are not customer identity at all.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.retrieval import EvidenceIndex, direct_identifiers
from identity.tests.test_trace_ownership import CUTOFF, HASH_A, META, graph, resolve  # noqa: F401
from ingest import evidence
from policy.conditions import identity_claims, subject_from
from state.engine import attribution_for, from_hit

B_PHONE = '+1 555 0100 002'


def record(fields, n=1):
    return evidence.make(META, f'$.records[{n}]', dict({'resource_id': 'account_501'}, **fields), 'json')


def hit_for(graph, fields, email='a.new@example.test'):
    res = resolve(graph, email)
    hits = [h for h in EvidenceIndex([record(fields)], graph=graph).find(res)]
    assert len(hits) == 1
    return hits[0], res


def assert_unsupported(h, res):
    assert attribution_for(h, res) == 'mixed_context'
    a = from_hit(h, res)
    assert a.state == 'UNKNOWN' and not a.supported


def test_subject_email_with_another_customers_phone_is_not_attributed(graph):
    # The Codex reproduction: right email, foreign phone.
    h, res = hit_for(graph, {'email': 'a.new@example.test', 'phone': B_PHONE})
    assert h.owner_conflict
    assert_unsupported(h, res)


@pytest.mark.parametrize('fields', [
    {'email': 'a.new@example.test', 'user_id': 'user_102'},
    {'email': 'a.new@example.test', 'email_hash': 'b' * 64},
    {'user_id': 'user_101', 'phone': B_PHONE},
    {'email': 'a.new@example.test', 'contact': {'phones': [B_PHONE]}},
    {'email': 'a.new@example.test', 'phone': '+1 555 0199 999'},     # unknown holder
], ids=['foreign-user-id', 'foreign-hash', 'user-id-foreign-phone', 'nested-foreign-phone', 'unknown-phone'])
def test_any_foreign_or_unknown_customer_identifier_blocks_state(graph, fields):
    h, res = hit_for(graph, fields)
    assert_unsupported(h, res)


def test_same_person_email_phone_hash_and_user_id_is_supported(graph):
    h, res = hit_for(graph, {'email': 'a.new@example.test', 'phone': '+1 555 0100 001', 'email_hash': HASH_A,
                             'user_id': 'user_101', 'profile': {'previous_phone': '+1 555 0100 009'}})
    assert not h.owner_conflict
    assert attribution_for(h, res) == 'direct_verified'
    assert from_hit(h, res).supported


def test_historical_alias_with_current_phone_is_one_person(graph):
    h, res = hit_for(graph, {'email': 'a.old@example.test', 'phone': '+1 555 0100 001'})
    assert attribution_for(h, res) == 'direct' and from_hit(h, res).supported


def test_shared_alias_is_an_owner_conflict(graph):
    # shared@ was held by user_102 and user_103: neither may claim the record.
    res = resolve(graph, 'b@example.test')
    [h] = EvidenceIndex([record({'email': 'shared@example.test'})], graph=graph).find(res)
    assert h.owner_conflict
    assert_unsupported(h, res)


def test_support_agent_metadata_is_not_customer_identity(graph):
    fields = {'requester_email': 'a.new@example.test',
              'agent_email': 'b@example.test', 'assigned_agent': {'email': 'b@example.test', 'phone': B_PHONE},
              'handled_by': 'user_102'}
    assert direct_identifiers(fields) == {('email', 'a.new@example.test')}
    assert identity_claims(fields) == {('email', 'a.new@example.test')}
    h, res = hit_for(graph, fields)
    assert not h.owner_conflict and from_hit(h, res).supported
    # The agent's own identifiers never give the agent a supported state on the record.
    res_b = resolve(graph, 'b@example.test')
    for h in EvidenceIndex([record(fields)], graph=graph).find(res_b):
        assert_unsupported(h, res_b)


def test_policy_attribution_rejects_the_foreign_phone(graph):
    res = resolve(graph)
    subject = subject_from(res)
    claims = identity_claims({'email': 'a.new@example.test', 'phone': B_PHONE})
    assert subject.attribution(claims) == 'FOREIGN'
    assert subject.attribution(identity_claims({'email': 'a.new@example.test', 'phone': '+1 555 0100 001'})) \
        == 'SUBJECT'


def test_null_hash_rendering_is_not_an_identifier():
    assert direct_identifiers({'email': 'a.new@example.test', 'email_hash': 'null'}) == \
        {('email', 'a.new@example.test')}
    assert direct_identifiers({'email_hash': '[REDACTED]'}) == set()
