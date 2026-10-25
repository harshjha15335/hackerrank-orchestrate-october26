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


# --- support documents that describe themselves as attachments ---------------

ATTACHMENT_TEXT = ('DELIVERY ADDRESS CORRECTION REQUEST\nSupport reference CS-1 / support_77\n'
                   f' Detail  {SUBJECT_EMAIL}\nContinued - Attachment properties and upload history\n'
                   ' Record  file correction.pdf\n Detail  uploader customer\n')


def document(text=ATTACHMENT_TEXT, origin='support_platform', resource='support_77'):
    return Observation('doc_evidence', 'evidence/documents/x.pdf', f'document:{resource}', T, None, resource,
                       None, None, (), {'resource_id': resource, 'text': text}, 'pdf', None, None, None, origin)


def test_owning_system_document_describing_an_attachment_classifies_it():
    result = classify([document()], 'support_platform', 'support_77', CATS, CMAP)
    assert (result.category, result.status, result.basis) == ('SUPPORT_ATTACHMENT', 'MAPPED', 'document_text')


def test_document_signal_needs_every_pattern_and_the_owning_origin():
    no_uploader = ATTACHMENT_TEXT.replace(' Detail  uploader customer\n', '')
    assert classify([document(no_uploader)], 'support_platform', 'support_77', CATS, CMAP).status == 'UNMAPPED'
    assert classify([document(origin='central_observability_export')], 'support_platform', 'support_77',
                    CATS, CMAP).status == 'UNMAPPED'
    assert classify([document(resource='support_78')], 'support_platform', 'support_77', CATS,
                    CMAP).status == 'UNMAPPED'


def test_subject_only_attachment_document_is_owned_by_the_subject():
    from policy.conditions import TRUE
    d = decide({}, 'support_platform', 'support_77', 'UNKNOWN', extra=(document(),))
    assert (d.category, d.rule_id, d.condition_outcome) == ('SUPPORT_ATTACHMENT', 'rule_06', TRUE)
    assert d.effective_action == 'DELETE' and d.compliance == UNRESOLVED   # state still unproven by M4


def test_attachment_document_naming_someone_else_is_not_subject_only():
    from policy.tests.test_policy import OTHER_EMAIL
    shared = ATTACHMENT_TEXT + f' Detail  {OTHER_EMAIL}\n'
    d = decide({}, 'support_platform', 'support_77', 'UNKNOWN', extra=(document(shared),))
    assert d.condition_outcome != 'TRUE' and d.compliance == UNRESOLVED


def test_redacted_message_text_is_not_content_without_shared_context():
    # Pre-M9 Phase 5: '[REDACTED]' hides whatever context the message had, so it
    # cannot make Rule 05 FALSE (which would decide a DELETE); it stays UNKNOWN.
    d = decide({'message_text': '[REDACTED]', 'subject_reference': 'user_9001'}, 'support_platform',
               'support_77', 'UNKNOWN', category='SUPPORT_MESSAGE')
    assert d.condition_outcome == UNKNOWN and d.effective_action is None
    plain = decide({'message_text': 'Please close my profile.', 'requester_email': SUBJECT_EMAIL},
                   'support_platform', 'support_77', 'PRESENT', category='SUPPORT_MESSAGE')
    assert plain.condition_outcome == 'FALSE' and plain.effective_action == 'DELETE'
