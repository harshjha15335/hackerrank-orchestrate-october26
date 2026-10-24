import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import IdentityValue, Resolution
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest import evidence

META = {'file_id':'synthetic_file','file_path':'evidence/fixture',
        'captured_at':'2026-01-02T00:00:00Z'}


def subject():
    return Resolution('synthetic_case','2026-01-02T00:00:00Z','user_A',('user_A',),
                      'resolved',{},(IdentityValue('email','a@example.test','a@example.test','snapshot'),))


def test_array_position_across_services_is_not_a_join():
    a=evidence.make(META,'$.service_exports.account_service.profile_lookups[0]',
                    {'resource_id':'synthetic_account','email':'a@example.test'},'json')
    b=evidence.make(META,'$.service_exports.analytics_platform.profiles[0]',
                    {'resource_id':'synthetic_other','email':None},'json')
    hits=EvidenceIndex([a,b]).find(subject())
    assert [h.observation.resource_id for h in hits]==['synthetic_account']


def test_same_trace_join_and_wrong_trace_rejection():
    a=evidence.make(META,'line:1',{'trace_id':'trace_A','lookup_key':'a@example.test'},'log')
    b=evidence.make(META,'line:2',{'trace_id':'trace_A','resource_id':'synthetic_account'},'log')
    c=evidence.make(META,'line:3',{'trace_id':'trace_B','resource_id':'synthetic_other'},'log')
    hits=EvidenceIndex([a,b,c]).find(subject())
    assert [h.observation.locator for h in hits]==['line:1','line:2']
    assert hits[1].strength=='correlated'


def test_shared_trace_with_two_customers_does_not_propagate():
    a=evidence.make(META,'line:1',{'trace_id':'trace_A','lookup_key':'a@example.test'},'log')
    b=evidence.make(META,'line:2',{'trace_id':'trace_A','lookup_key':'b@example.test'},'log')
    c=evidence.make(META,'line:3',{'trace_id':'trace_A','resource_id':'synthetic_unknown'},'log')
    assert [h.observation.locator for h in EvidenceIndex([a,b,c]).find(subject())]==['line:1']


def test_multi_person_pdf_never_creates_document_join(monkeypatch):
    text='Support reference support_101\na@example.test\nOther person b@example.test\n'
    monkeypatch.setattr(evidence.subprocess,'run',lambda *args,**kwargs: SimpleNamespace(stdout=text))
    observations,status=evidence.parse_pdf(Path('/tmp/synthetic.pdf'),META)
    assert status=='parsed'
    assert not any(o.locator.startswith('document:') for o in observations)
    assert not any(h.observation.resource_id=='support_101' for h in EvidenceIndex(observations).find(subject()))


def test_one_email_but_multiple_user_references_is_not_single_subject(monkeypatch):
    text='Support reference support_101\na@example.test\nuser_100\nuser_200\n'
    monkeypatch.setattr(evidence.subprocess,'run',lambda *args,**kwargs: SimpleNamespace(stdout=text))
    observations,_=evidence.parse_pdf(Path('/tmp/synthetic.pdf'),META)
    assert not any(o.locator.startswith('document:') for o in observations)


def test_single_subject_pdf_retains_explicit_reference(monkeypatch):
    text='Support reference support_101\na@example.test\n'
    monkeypatch.setattr(evidence.subprocess,'run',lambda *args,**kwargs: SimpleNamespace(stdout=text))
    observations,_=evidence.parse_pdf(Path('/tmp/synthetic.pdf'),META)
    hits=EvidenceIndex(observations).find(subject())
    assert any(h.observation.resource_id=='support_101' and h.observation.locator=='document:support_101'
               for h in hits)


def test_negative_sql_scope_requires_independent_resource_reference():
    present=evidence.make(META,'customer_profiles[1]',{'resource_id':'synthetic_present'},'sql')
    coverage=[{'format':'.sql','file_id':'synthetic_file','source_path':'evidence/fixture',
               'tables':{'customer_profiles':1}}]
    index=SnapshotIndex([present],coverage)
    assert index.scope('synthetic_file','customer_profiles','2026-01-02T00:00:00Z')
    assert index.absence_candidate('synthetic_file','customer_profiles','synthetic_missing',
                                   '2026-01-02T00:00:00Z') is None
    reference=evidence.make({**META,'file_id':'synthetic_other'},'row:1',
                            {'resource_id':'synthetic_missing','email':'a@example.test'},'json')
    assert index.absence_candidate('synthetic_file','customer_profiles','synthetic_missing',
                                   '2026-01-02T00:00:00Z',source_reference=reference)
    candidate=index.absence_candidate('synthetic_file','customer_profiles','synthetic_missing',
                                      '2026-01-02T00:00:00Z',source_reference=reference)
    assert not hasattr(candidate,'user_id') and not hasattr(candidate,'state')
    unrelated=evidence.make({**META,'file_id':'synthetic_unrelated'},'row:2',
                            {'resource_id':'synthetic_missing','email':'other@example.test'},'json')
    assert index.absence_candidate('synthetic_file','customer_profiles','synthetic_missing',
                                   '2026-01-02T00:00:00Z',source_reference=unrelated)==candidate
    assert index.absence_candidate('synthetic_file','customer_profiles','synthetic_present',
                                   '2026-01-02T00:00:00Z',source_reference=present) is None
    assert index.scope('synthetic_file','customer_profiles','2026-01-01T23:59:59Z') is None


# --- trace anchors must be evidence at the cutoff (M6 safety correction) -----

LATE_META = {'file_id': 'synthetic_file', 'file_path': 'evidence/fixture', 'captured_at': '2026-01-05T00:00:00Z'}


def trace_lines(anchor_time, *, meta=LATE_META, anchor_email='a@example.test'):
    anchor = evidence.make(meta, 'line:2', {'trace_id': 'tr-1', 'lookup_key': anchor_email}, 'log',
                           event_time=anchor_time)
    member = evidence.make(meta, 'line:1', {'trace_id': 'tr-1', 'resource_id': 'synthetic_account'}, 'log',
                           event_time='2026-01-01T00:00:00Z')
    return anchor, member


def resolved_at(cutoff):
    return Resolution('synthetic_case', cutoff, 'user_A', ('user_A',), 'resolved', {},
                      (IdentityValue('email', 'a@example.test', 'a@example.test', 'snapshot'),))


def correlated(hits):
    return [h.observation.locator for h in hits if h.strength == 'correlated']


def test_post_cutoff_trace_anchor_does_not_correlate():
    anchor, member = trace_lines('2026-01-06T00:00:00Z', meta={**LATE_META, 'captured_at': '2026-01-07T00:00:00Z'})
    assert correlated(EvidenceIndex([anchor, member]).find(resolved_at('2026-01-07T00:00:00Z'))) == ['line:1']
    assert correlated(EvidenceIndex([anchor, member]).find(resolved_at('2026-01-05T12:00:00Z'))) == []


def test_trace_anchor_after_its_capture_does_not_correlate():
    anchor, member = trace_lines('2026-01-06T00:00:00Z')
    assert correlated(EvidenceIndex([anchor, member]).find(resolved_at('2026-02-01T00:00:00Z'))) == []


def test_quarantined_trace_anchor_does_not_correlate():
    anchor, member = trace_lines('2026-01-02T00:00:00Z')
    index = EvidenceIndex([anchor, member], anomalies={(anchor.evidence_id, anchor.locator)})
    assert correlated(index.find(resolved_at('2026-02-01T00:00:00Z'))) == []
    assert correlated(EvidenceIndex([anchor, member]).find(resolved_at('2026-02-01T00:00:00Z'))) == ['line:1']


def test_inadmissible_foreign_anchor_does_not_block_valid_join():
    anchor, member = trace_lines('2026-01-02T00:00:00Z')
    foreign = evidence.make(LATE_META, 'line:3', {'trace_id': 'tr-1', 'lookup_key': 'b@example.test'}, 'log',
                            event_time='2026-01-06T00:00:00Z')
    hits = EvidenceIndex([anchor, member, foreign]).find(resolved_at('2026-02-01T00:00:00Z'))
    assert correlated(hits) == ['line:1']
