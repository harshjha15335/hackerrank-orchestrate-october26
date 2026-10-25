"""Rule 12 when no retention period is supplied (owner policy decision).

deletion_rules.csv has no rule that authorizes deleting a SECURITY_AUDIT_LOG,
so an observed, subject-attributed security audit record with no supplied
period is preserved (RETAIN, verified PRESENT). No period is invented: an
expired period is still not retained, and missing field evidence stays UNKNOWN.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policy.conditions import FALSE, TRUE, UNKNOWN, load_config
from policy.engine import COMPLIANT, UNRESOLVED, VIOLATION
from policy.tests.test_policy import SUBJECT, decide, ops

SYS, RES = 'security_service', 'audit_record_9'
UNKNOWN_MODE = dict(load_config(), retention_without_period='unknown')
SHIPPED = load_config()


def test_default_mode_preserves_observed_record_without_period():
    assert load_config()['retention_without_period'] == 'retain_observed_without_period'
    d = decide({'subject_reference': SUBJECT}, SYS, RES, 'PRESENT', bindings=SHIPPED)
    assert (d.rule_id, d.condition_outcome, d.effective_action) == ('rule_12', TRUE, 'RETAIN')
    assert d.compliance == COMPLIANT and ops(d) == ['VERIFY_RECORD_PRESENT']
    assert 'no supplied retention period' in d.condition_reason


def test_expired_period_is_never_retained():
    d = decide({'subject_reference': SUBJECT, 'retention_until': '2026-01-01T00:00:00Z'}, SYS, RES, 'PRESENT',
               bindings=SHIPPED)
    assert d.condition_outcome == FALSE and d.compliance == VIOLATION
    assert ops(d) == ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']


def test_no_field_evidence_stays_unknown():
    d = decide({}, SYS, RES, 'UNKNOWN', category='SECURITY_AUDIT_LOG', bindings=SHIPPED)
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED and ops(d) == []


def test_unknown_mode_keeps_previous_behaviour():
    d = decide({'subject_reference': SUBJECT}, SYS, RES, 'PRESENT', bindings=UNKNOWN_MODE)
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED and ops(d) == []


def test_supplied_valid_period_still_decides():
    d = decide({'subject_reference': SUBJECT, 'retention_until': '2031-01-01T00:00:00Z'}, SYS, RES, 'PRESENT',
               bindings=SHIPPED)
    assert d.condition_outcome == TRUE and 'covers audit_at' in d.condition_reason
