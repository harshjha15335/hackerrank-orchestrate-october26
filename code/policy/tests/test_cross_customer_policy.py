"""Codex re-test: another customer's identifier on a record keeps policy and
citations from treating it as the subject's (no COMPLIANT, no finding)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policy.engine import COMPLIANT, UNRESOLVED
from policy.tests.test_anonymization import NULLED, RESOURCE, SYSTEM, activity
from policy.tests.test_policy import SUBJECT_EMAIL, decide

FOREIGN_PHONE = '+1 555 0199 999'


@pytest.mark.parametrize('attribution', ['direct', 'direct_verified', 'correlated'])
@pytest.mark.parametrize('state', ['PRESENT', 'ABSENT', 'ANONYMIZED'])
def test_subject_email_with_foreign_phone_decides_nothing(attribution, state):
    fields = dict(NULLED, email=SUBJECT_EMAIL, phone=FOREIGN_PHONE)
    d = decide(fields, SYSTEM, RESOURCE, state, attribution=attribution, extra=(activity(),))
    assert d.compliance == UNRESOLVED and d.obligations == ()


def test_nested_foreign_phone_blocks_compliant_anonymization():
    fields = dict(NULLED, context={'contact': {'phone': FOREIGN_PHONE}})
    d = decide(fields, SYSTEM, RESOURCE, 'ANONYMIZED', attribution='direct', extra=(activity(),))
    assert d.compliance != COMPLIANT
