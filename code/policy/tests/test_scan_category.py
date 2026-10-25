"""Pre-M9 Phase 3: support records known only from the owning service's content scan.

A support_platform ``message_pii_scan`` of a resource scans that record's
message, so the record is a SUPPORT_MESSAGE. The mapping is declarative
(category_map.json scan_event_signals), keyed by event and owning system, and
ranks below every record-level signal. It decides the category only: the Rule
05 shared-context condition still needs conversation content and stays UNKNOWN.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ingest.evidence import Observation
from policy.categories import classify, load_map
from policy.conditions import UNKNOWN
from policy.engine import UNRESOLVED
from policy.rules import load_rules
from policy.tests.test_policy import RULES, SUBJECT_EMAIL, T, decide

CATS = load_rules(RULES).categories
CMAP = load_map()


def scan(event='message_pii_scan', service='support_platform', resource='support_77', **extra):
    raw = {'event': event, 'service': service, 'resource_id': resource, 'matched_value': SUBJECT_EMAIL,
           'detector': 'direct_identifier', 'trace_id': 'tr-1', **extra}
    return Observation('scan_evidence', 'evidence/logs/x.log', 'line:7', T, service, resource, None, None, (),
                       raw, 'log', None, None, '2026-09-10T11:00:00Z', 'central_observability_export')


def test_message_scan_classifies_support_message():
    result = classify([scan()], 'support_platform', 'support_77', CATS, CMAP)
    assert (result.category, result.status, result.basis) == ('SUPPORT_MESSAGE', 'MAPPED', 'scan_event')


def test_attachment_scan_does_not_classify_the_record():
    result = classify([scan('attachment_pii_scan', file='receipt.pdf')], 'support_platform', 'support_77',
                      CATS, CMAP)
    assert result.status == 'UNMAPPED'


def test_scan_by_another_service_or_of_another_resource_is_ignored():
    assert classify([scan(service='search_service')], 'support_platform', 'support_77', CATS,
                    CMAP).status == 'UNMAPPED'
    assert classify([scan(resource='support_78')], 'support_platform', 'support_77', CATS,
                    CMAP).status == 'UNMAPPED'


def test_record_fields_outrank_the_scan():
    attachment = Observation('rec', 'evidence/r.json', '$.a[0]', T, 'support_platform', 'support_77', None, None,
                             (), {'resource_id': 'support_77', 'file_name': 'x.pdf'}, 'json')
    result = classify([scan(), attachment], 'support_platform', 'support_77', CATS, CMAP)
    assert (result.category, result.basis) == ('SUPPORT_ATTACHMENT', 'record_fields')


def test_scan_alone_leaves_shared_context_unknown():
    # Policy fixtures model the scanned support record with no conversation fields.
    d = decide({}, 'support_platform', 'support_77', 'UNKNOWN', extra=(scan(),))
    assert d.category == 'SUPPORT_MESSAGE' and d.rule_id == 'rule_05'
    assert d.condition_outcome == UNKNOWN and d.compliance == UNRESOLVED and d.obligations == ()
