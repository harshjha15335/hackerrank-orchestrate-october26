"""F-02 (pre-M9 audit): Rule 07/08 anonymization needs evidence, not null columns.

Five source-grounded states are distinguished (conditions.anonymization_state):
direct identifiers exposed, indirect identifiers re-linking, indirect identifiers
present, identifiers removed or merely not displayed, and an independently
corroborated anonymization operation. Only the last is FALSE ("no longer
attributable"); everything short of it is UNKNOWN and never compliant.
"""
import socket
from dataclasses import replace
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ingest.evidence import Observation
from policy.conditions import FALSE, TRUE, UNKNOWN
from policy.engine import COMPLIANT, UNRESOLVED, VIOLATION, Context, decide_copy, rollup
from policy.conditions import subject_from
from policy.tests.test_policy import (OTHER_EMAIL, RULES, SUBJECT, SUBJECT_EMAIL, T, decide, obs, ops,
                                      resolution)

NULLED = {'user_id': None, 'email': None, 'phone': None, 'email_hash': None,
          'reporting_window': 'last_90_days', 'metrics': {'sessions_30d': 3}}
SYSTEM, RESOURCE = 'analytics_platform', 'analytics_77'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))


def activity(event_type='ANONYMIZE_RECORD', result='SUCCESS', when='2026-09-08T10:00:00Z',
             system=SYSTEM, resource=RESOURCE, activity_id='activity_9001'):
    raw = {'activity_id': activity_id, 'event_time': when, 'event_type': event_type,
           'source_system': 'deletion_worker', 'target_system': system, 'resource_id': resource,
           'reported_result': result, 'details': f'Policy action completed for {resource}.'}
    return Observation(activity_id, 'system_activity.csv', 'row:1', when, None, resource, None, None, (), raw,
                       'activity', None, None, when, 'system_activity')


def test_null_identifier_columns_alone_are_not_anonymization():
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED')
    assert d.condition_outcome == UNKNOWN and d.condition_reason.startswith('DIRECT_REMOVED')
    assert d.compliance == UNRESOLVED and ops(d) == []


def test_identifiers_not_displayed_is_not_removal():
    d = decide({'reporting_window': 'last_90_days', 'metrics': {'x': 1}}, SYSTEM, RESOURCE, 'ANONYMIZED')
    assert d.condition_outcome == UNKNOWN and d.condition_reason.startswith('NOT_DISPLAYED')
    assert d.compliance == UNRESOLVED


def test_corroborated_operation_is_anonymized():
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    assert d.condition_outcome == FALSE and d.condition_reason.startswith('ANONYMIZATION_EVIDENCED')
    assert 'activity_9001' in d.condition_evidence
    assert d.compliance == COMPLIANT and ops(d) == ['VERIFY_RECORD_ANONYMIZED']


def test_telemetry_uses_the_same_proof():
    fields = {'user_id': None, 'email': None, 'metrics': {'clicks': 3}}
    plain = decide(fields, 'telemetry_service', 'telemetry_9', 'PRESENT')
    proven = decide(fields, 'telemetry_service', 'telemetry_9', 'PRESENT',
                    extra=(activity(system='telemetry_service', resource='telemetry_9'),))
    assert (plain.category, plain.compliance) == ('PRODUCT_TELEMETRY', UNRESOLVED)
    assert (proven.condition_outcome, proven.compliance) == (FALSE, COMPLIANT)


@pytest.mark.parametrize('op', [
    activity(result='FAILED'),                                   # failed operation
    activity(event_type='REDACT_RECORD'),                        # not an anonymization
    activity(system='search_service'),                           # another system's copy
    activity(resource='analytics_78'),                           # another record
    activity(when='2026-09-10T13:00:00Z'),                       # after audit_at
], ids=['failed', 'redaction', 'other-system', 'other-resource', 'future'])
def test_operation_must_match_and_precede(op):
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(op,))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED


def test_operation_after_the_source_read_does_not_corroborate_it():
    # The read (captured at T) must post-date the operation it corroborates.
    o = obs(NULLED, SYSTEM, RESOURCE, captured='2026-09-08T09:00:00Z')
    ctx = Context([o, activity(when='2026-09-08T10:00:00Z')], RULES)
    latest = {'system_id': SYSTEM, 'resource_id': RESOURCE, 'topology': 'service', 'state': 'ANONYMIZED',
              'supported': True, 'explanation': 'synthetic', 'evidence_id': o.evidence_id,
              'locator': o.locator, 'attribution': 'correlated'}
    res = resolution()
    d = decide_copy(ctx, latest, [latest], res, subject_from(res))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED


def test_direct_identifier_still_exposed_is_attributable():
    d = decide(dict(NULLED, email=SUBJECT_EMAIL), SYSTEM, RESOURCE, 'PRESENT', extra=(activity(),))
    assert d.condition_outcome == TRUE and d.compliance == VIOLATION
    assert ops(d) == ['REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED']


def test_indirect_identifier_linked_to_subject_elsewhere_is_attributable():
    device = 'dev-4417-a9'
    elsewhere = obs({'email': SUBJECT_EMAIL, 'device_id': device}, 'support_platform', 'support_5',
                    evidence='other_evidence', locator='$.tickets[0]')
    d = decide(dict(NULLED, device_id=device), SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), elsewhere))
    assert d.condition_outcome == TRUE and d.condition_reason.startswith('INDIRECT_LINKED')
    assert d.compliance == VIOLATION


def test_indirect_identifier_linked_only_to_someone_else_is_unknown():
    device = 'dev-4417-a9'
    elsewhere = obs({'email': OTHER_EMAIL, 'device_id': device}, 'support_platform', 'support_5',
                    evidence='other_evidence', locator='$.tickets[0]')
    d = decide(dict(NULLED, device_id=device), SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), elsewhere))
    assert d.condition_outcome == UNKNOWN and d.condition_reason.startswith('INDIRECT_PRESENT')
    assert d.compliance == UNRESOLVED


def test_future_link_record_is_not_evidence():
    device = 'dev-4417-a9'
    future = obs({'email': SUBJECT_EMAIL, 'device_id': device}, 'support_platform', 'support_5',
                 evidence='other_evidence', locator='$.tickets[0]', captured='2026-09-11T00:00:00Z')
    d = decide(dict(NULLED, device_id=device), SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), future))
    assert d.condition_reason.startswith('INDIRECT_PRESENT') and d.compliance == UNRESOLVED


def test_historical_copy_naming_subject_after_operation_relinks():
    later = obs(dict(NULLED, email=SUBJECT_EMAIL), SYSTEM, RESOURCE, evidence='replica_evidence',
                locator='$.records[3]', captured='2026-09-09T00:00:00Z')
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), later))
    assert d.condition_outcome == UNKNOWN and d.condition_reason.startswith('DIRECT_REMOVED')
    assert d.compliance == UNRESOLVED


def test_historical_copy_before_operation_is_superseded():
    earlier = obs(dict(NULLED, email=SUBJECT_EMAIL), SYSTEM, RESOURCE, evidence='old_evidence',
                  locator='$.records[3]', captured='2026-09-01T00:00:00Z')
    d = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(), earlier))
    assert (d.condition_outcome, d.compliance) == (FALSE, COMPLIANT)


def test_missing_state_is_unresolved():
    d = decide(NULLED, SYSTEM, RESOURCE, 'UNKNOWN', extra=(activity(),))
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED


def test_absent_copy_without_field_evidence_stays_unresolved():
    # Unchanged M5 behaviour: with no field set the condition is UNKNOWN, so no
    # treatment is decided even for an ABSENT copy (never a guessed compliance).
    d = decide({}, SYSTEM, RESOURCE, 'ABSENT', category='ANALYTICS_PROFILE')
    assert (d.condition_outcome, d.compliance) == (UNKNOWN, UNRESOLVED)


def test_multiple_copies_worst_copy_decides():
    proven = decide(NULLED, SYSTEM, RESOURCE, 'ANONYMIZED', extra=(activity(),))
    exposed = decide(dict(NULLED, email=SUBJECT_EMAIL), SYSTEM, RESOURCE, 'PRESENT', extra=(activity(),))
    replica = replace(exposed, topology='replica')
    [resource] = rollup([proven, replica])
    assert resource['compliance'] == VIOLATION and resource['copies'] == 2
    assert resource['deciding_copy']['topology'] == 'replica'
