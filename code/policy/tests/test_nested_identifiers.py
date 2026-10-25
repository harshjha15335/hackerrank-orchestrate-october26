"""Codex re-test: nested identifiers must not bypass Rule 07/08 anonymization.

Indirect identifiers (session, device, linkage keys), direct identifiers and
stable references are found at any depth of nested objects and arrays. A
nested linkage key blocks ANONYMIZATION_EVIDENCED: re-linked to the subject
it is TRUE (violation); otherwise the outcome stays UNKNOWN. Benign metrics
and unnamed numbers are never treated as identities.
"""
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policy.conditions import FALSE, TRUE, UNKNOWN, indirect_identifiers, load_config
from policy.engine import COMPLIANT, UNRESOLVED, VIOLATION
from policy.tests.test_anonymization import NULLED, RESOURCE, SYSTEM, activity
from policy.tests.test_policy import OTHER_EMAIL, SUBJECT_EMAIL, decide, obs

CONFIG = load_config()
SESSION = 'sess-7Q2K-91XA'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))


def elsewhere(fields, email=SUBJECT_EMAIL, captured=None):
    extra = {'captured': captured} if captured else {}
    return obs(dict(fields, email=email), 'support_platform', 'support_5', evidence='other_evidence',
               locator='$.tickets[0]', **extra)


@pytest.mark.parametrize('fields', [
    {'session_id': SESSION},
    {'context': {'session_id': SESSION}},
    {'context': {'client': {'device': {'device_id': SESSION}}}},
    {'events': [{'kind': 'view'}, {'kind': 'buy', 'session_id': SESSION}]},
    {'context': {'source_session_id': SESSION}},
    {'links': [{'linkage_key': SESSION}]},
], ids=['top-level', 'nested', 'deep', 'array', 'suffixed', 'linkage-key'])
def test_nested_linkage_key_blocks_evidenced_anonymization(fields):
    d = decide(dict(NULLED, **fields), SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    assert d.condition_outcome == UNKNOWN and d.condition_reason.startswith('INDIRECT_PRESENT')
    assert d.compliance == UNRESOLVED


@pytest.mark.parametrize('copied', [
    {'session_id': SESSION},
    {'meta': {'sessions': [{'session_id': SESSION}]}},
    {'source_session_id': SESSION},
], ids=['flat-copy', 'nested-copy', 'renamed-copy'])
def test_nested_key_copied_next_to_subject_identifiers_is_violation(copied):
    d = decide(dict(NULLED, context={'session_id': SESSION}), SYSTEM, RESOURCE, 'ANONYMIZED',
               extra=(activity(), elsewhere(copied)))
    assert d.condition_outcome == TRUE and d.condition_reason.startswith('INDIRECT_LINKED')
    assert d.compliance == VIOLATION


def test_nested_key_copied_next_to_someone_else_stays_unknown():
    d = decide(dict(NULLED, context={'session_id': SESSION}), SYSTEM, RESOURCE, 'ANONYMIZED',
               extra=(activity(), elsewhere({'session_id': SESSION}, email=OTHER_EMAIL)))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED


def test_nested_direct_identifier_is_exposed():
    d = decide(dict(NULLED, context={'customer': [{'email': SUBJECT_EMAIL}]}), SYSTEM, RESOURCE, 'ANONYMIZED',
               extra=(activity(),))
    assert d.condition_outcome == TRUE and d.condition_reason.startswith('DIRECT_EXPOSED')
    assert d.compliance == VIOLATION


def test_activity_success_alone_is_not_anonymization():
    d = decide({}, SYSTEM, RESOURCE, 'UNKNOWN', category='ANALYTICS_PROFILE', extra=(activity(),))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED
    shown = decide({'metrics': {'sessions_30d': 3}}, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    assert shown.condition_reason.startswith('NOT_DISPLAYED') and shown.compliance == UNRESOLVED


def test_later_nested_identifying_copy_is_not_ignored():
    later = obs(dict(NULLED, profile_copy={'contact': {'email': SUBJECT_EMAIL}}), SYSTEM, RESOURCE,
                evidence='replica_evidence', locator='$.records[3]', captured='2026-09-09T00:00:00Z')
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), later))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED


def test_benign_metrics_are_not_identities():
    fields = dict(NULLED, metrics={'sessions_30d': 3, 'session_count': 12, 'avg_session_seconds': 41.5,
                                   'device_count': 2, 'conversion_rate': 0.031},
                  flags={'session_id': True, 'device_id': 0.5})
    assert indirect_identifiers(fields, CONFIG) == []
    d = decide(fields, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    assert (d.condition_outcome, d.compliance) == (FALSE, COMPLIANT)


def test_redacted_nested_key_is_not_an_identifier():
    d = decide(dict(NULLED, context={'session_id': '[REDACTED]'}), SYSTEM, RESOURCE, 'ANONYMIZED',
               extra=(activity(),))
    assert (d.condition_outcome, d.compliance) == (FALSE, COMPLIANT)


def test_corroborated_anonymization_still_works():
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    assert d.condition_outcome == FALSE and d.compliance == COMPLIANT
    assert 'activity_9001' in d.condition_evidence


def test_nested_paths_are_reported():
    found = indirect_identifiers({'a': {'b': [{'session_id': 'S-1'}, {'device_id': 77}]}}, CONFIG)
    assert found == [('a.b[0].session_id', 'S-1'), ('a.b[1].device_id', '77')]
