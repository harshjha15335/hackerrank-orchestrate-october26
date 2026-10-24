import csv
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import IdentityGraph, norm
from identity.retrieval import EvidenceIndex
from ingest.evidence import ingest, make

DATASET = Path(__file__).resolve().parents[3] / 'dataset'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs): raise AssertionError('network call during M2')
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def fixture_dataset(tmp_path):
    folder = tmp_path / 'dataset';folder.mkdir()
    with (folder / 'user_identities.csv').open('w', newline='') as f:
        w=csv.writer(f);w.writerow(['user_id','name','email','phone','email_hash','updated_at'])
        w.writerow(['user_A','Same Name','new@example.test','+1 555 222 0000','hash-new','2026-03-01T00:00:00Z'])
        w.writerow(['user_B','Same Name','new.jr@example.test','+1 555 222 0001','hash-other','2026-01-01T00:00:00Z'])
    with (folder / 'user_audit_log.csv').open('w', newline='') as f:
        w=csv.writer(f);w.writerow(['audit_id','user_id','event_time','field_name','old_value','new_value'])
        w.writerows([['synthetic_a','user_A','2026-02-01T00:00:00Z','email','old@example.test','middle@example.test'],
                     ['synthetic_b','user_A','2026-03-01T00:00:00Z','email','middle@example.test','new@example.test'],
                     ['synthetic_c','user_A','2026-03-01T00:00:00Z','phone','+1 555 111 0000','+1 555 222 0000'],
                     ['synthetic_d','user_A','2026-03-01T00:00:00Z','email_hash','hash-old','hash-new']])
    return folder


def case(email, cutoff, name='synthetic_case'):
    return {'case_id':name,'email':email,'audit_at':cutoff}


def test_historical_chain_and_future_exclusion(tmp_path):
    graph=IdentityGraph(fixture_dataset(tmp_path))
    early=graph.resolve(case('OLD@EXAMPLE.TEST','2026-01-15T00:00:00Z'))
    assert early.user_id=='user_A' and early.current_at_cutoff['email']=='old@example.test'
    assert {v.original for v in early.history if v.field=='email'}=={'old@example.test'}
    middle=graph.resolve(case('middle@example.test','2026-02-15T00:00:00Z'))
    assert middle.user_id=='user_A' and middle.current_at_cutoff['email']=='middle@example.test'
    assert {v.original for v in middle.history if v.field=='email'}=={'old@example.test','middle@example.test'}
    assert graph.resolve(case('new@example.test','2026-02-15T00:00:00Z')).status=='unresolved'
    assert graph.resolve(case('new@example.test','2026-03-01T00:00:00Z')).user_id=='user_A'


def test_normalization_and_decoys(tmp_path):
    graph=IdentityGraph(fixture_dataset(tmp_path))
    assert norm('phone','+1 (555) 222-0000')=='15552220000'
    assert norm('email','NEW@EXAMPLE.TEST')=='new@example.test'
    assert norm('email_hash','ABCDEF')=='ABCDEF'
    assert norm('email_hash','abcdef')!='ABCDEF'
    cutoff='2026-04-01T00:00:00Z'
    for near in ('ne@example.test','new.j@example.test','xnew@example.test','new@example.tests','middle@example.tes'):
        assert graph.resolve(case(near,cutoff)).status=='unresolved'
    assert graph.resolve(case('new.jr@example.test',cutoff)).user_id=='user_B'


def test_ambiguity_is_explicit(tmp_path):
    folder=fixture_dataset(tmp_path)
    with (folder/'user_identities.csv').open('a',newline='') as f:
        csv.writer(f).writerow(['user_C','Other','new@example.test','','','2026-01-01T00:00:00Z'])
    r=IdentityGraph(folder).resolve(case('new@example.test','2026-04-01T00:00:00Z'))
    assert r.status=='ambiguous' and r.user_id is None and r.candidates==('user_A','user_C')


def test_index_exact_keys_cutoff_and_context(tmp_path):
    graph=IdentityGraph(fixture_dataset(tmp_path))
    meta={'file_id':'synthetic_file','file_path':'evidence/synthetic','captured_at':'2026-02-15T00:00:00Z'}
    obs=[make(meta,'row:1',{'resource_id':'synthetic_a','email':'OLD@EXAMPLE.TEST'},'json'),
         make(meta,'row:2',{'resource_id':'synthetic_b','email':'old.jr@example.test'},'json'),
         make({**meta,'captured_at':'2026-02-16T00:00:00Z'},'row:3',
              {'resource_id':'synthetic_c','email':'old@example.test'},'json')]
    index=EvidenceIndex(obs)
    r=graph.resolve(case('middle@example.test','2026-02-15T00:00:00Z'))
    hits=index.find(r)
    assert [h.observation.resource_id for h in hits]==['synthetic_a']
    assert hits[0].strength=='direct' and hits[0].observation.locator=='row:1'


def test_unrelated_identifiers_on_one_record_are_flagged(tmp_path):
    graph=IdentityGraph(fixture_dataset(tmp_path))
    meta={'file_id':'synthetic_file','file_path':'evidence/synthetic','captured_at':'2026-04-01T00:00:00Z'}
    observation=make(meta,'line:1',{'resource_id':'synthetic_shared',
        'lookup_key':'new@example.test','other_email':'new.jr@example.test'},'log')
    index=EvidenceIndex([observation])
    hits=index.find(graph.resolve(case('new@example.test','2026-04-01T00:00:00Z')))
    assert len(hits)==1 and hits[0].strength=='mixed_context'


def test_duplicate_subject_cases_do_not_share_cutoff(tmp_path):
    graph=IdentityGraph(fixture_dataset(tmp_path))
    early=graph.resolve(case('old@example.test','2026-01-15T00:00:00Z','synthetic_early'))
    late=graph.resolve(case('old@example.test','2026-04-01T00:00:00Z','synthetic_late'))
    assert early.user_id==late.user_id
    assert early.case_id!=late.case_id
    assert early.current_at_cutoff['email']!=late.current_at_cutoff['email']


def test_full_resolution_and_independent_historical_recount():
    graph=IdentityGraph(DATASET)
    rows=graph.requests(); result=[graph.resolve(r) for r in rows]
    assert len(rows)==518 and all(r.status=='resolved' for r in result)
    current={u['email'].casefold() for u in graph.users.values()}
    historical=[r for r in rows if r['email'].casefold() not in current]
    assert len(historical)==100  # actual current CSV count; older checkpoint says 95
    assert all(graph.resolve(r).user_id for r in historical[:10])
    for r in historical[:10]:
        resolution=graph.resolve(r)
        assert any(a['field_name']=='email' and a['old_value'].casefold()==r['email'].casefold()
                   for a in graph.audit[resolution.user_id])


def test_repeatable_reference_digest_and_cutoff():
    graph=IdentityGraph(DATASET); obs,_,_=ingest(DATASET); index=EvidenceIndex(obs)
    rows=graph.requests(True)[:2]
    results=[]
    for case_row in rows:
        hits=index.find(graph.resolve(case_row))
        assert all(h.observation.captured_at <= case_row['audit_at'] for h in hits)
        results.append([(h.observation.evidence_id,h.observation.locator,h.strength) for h in hits])
    digest=lambda data:hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    assert digest(results)==digest([[(h.observation.evidence_id,h.observation.locator,h.strength)
                                    for h in index.find(graph.resolve(r))] for r in rows])
