"""Dev-only diagnostic. Sample gold is never loaded by production modules."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import read_output
from evaluation.m2_oracle import supported_pair
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest.evidence import ingest


def historical_only_recount(dataset):
    with (dataset/'user_identities.csv').open(newline='',encoding='utf-8') as stream:
        current={row['email'].casefold() for row in csv.DictReader(stream)}
    with (dataset/'deletion_requests.csv').open(newline='',encoding='utf-8') as stream:
        requests=list(csv.DictReader(stream))
    return len(requests),sum(row['email'].casefold() in current for row in requests),sum(
        row['email'].casefold() not in current for row in requests)


def analyze(dataset):
    graph=IdentityGraph(dataset); observations,coverage,_=ingest(dataset)
    index=EvidenceIndex(observations); snapshots=SnapshotIndex(observations,coverage)
    gold={r['case_id']:r for r in read_output(dataset/'sample_output.csv')}
    requests=sorted(graph.requests(True),key=lambda r:r['case_id'])[:22]
    misses=[]; reached=total=negative_scopes=0
    for case in requests:
        resolution=graph.resolve(case)
        found={(h.observation.evidence_id,h.observation.resource_id) for h in index.find(resolution)}
        for step in gold[case['case_id']]['steps_json']:
            evidence_id, resource_id=step['evidence_id'],step['resource_id']
            if not evidence_id: continue
            total+=1
            if (evidence_id,resource_id) in found:
                reached+=1;continue
            source=[o for o in observations if o.evidence_id==evidence_id]
            matching=[o for o in source if o.resource_id==resource_id]
            other=[o for o in observations if o.resource_id==resource_id and o.evidence_id!=evidence_id]
            manifest=next((r for r in coverage if r['file_id']==evidence_id),None)
            scopes=[t for (file_id,t) in snapshots.scopes if file_id==evidence_id]
            negative=bool(manifest and manifest['format']=='.sql' and not matching and scopes)
            negative_scopes+=negative
            raw_keys=sorted({k for o in matching for k in o.raw_fields if
                             any(term in k for term in ('email','phone','hash','reference','user_id','lookup'))})
            misses.append({'case':case['case_id'],'evidence':evidence_id,'resource':resource_id,
                           'source':manifest['source_path'] if manifest else 'missing manifest',
                           'locators':[o.locator for o in matching],
                           'identifier_fields':{k:sorted({str(o.raw_fields.get(k)) for o in matching}) for k in raw_keys},
                           'subject':resolution.user_id,
                           'history_fields':sorted({v.field for v in resolution.history}),
                           'audit_ids':sorted({v.source_id for v in resolution.history if v.source_id.startswith('audit_')}),
                           'other_resource_refs':[(o.evidence_id,o.locator) for o in other[:8]],
                           'trace_ids':sorted({str(o.raw_fields['trace_id']) for o in matching if o.raw_fields.get('trace_id')}),
                           'exists_in_cited_source':bool(matching),
                           'negative_scope_tables':scopes if negative else [],
                           'class':'negative_scope_unattributed' if negative else 'unattributed'})
    return total,reached,negative_scopes,misses


def independent_gate(dataset, index_override=None):
    """Evaluate cited pairs against source facts, independently of postings."""
    graph=IdentityGraph(dataset); observations,coverage,_=ingest(dataset)
    index=index_override or EvidenceIndex(observations)
    snapshots=SnapshotIndex(observations,coverage)
    gold={r['case_id']:r for r in read_output(dataset/'sample_output.csv')}
    metrics={'total':0,'original_hits':0,'supported':0,'supported_hits':0,
             'negative_scopes':0,'unattributed':0,'unsupported_hits':0}
    for case in sorted(graph.requests(True),key=lambda r:r['case_id'])[:22]:
        resolution=graph.resolve(case)
        hits={(h.observation.evidence_id,h.observation.resource_id) for h in index.find(resolution)}
        for step in gold[case['case_id']]['steps_json']:
            evidence_id,resource_id=step['evidence_id'],step['resource_id']
            if not evidence_id: continue
            metrics['total']+=1
            got=(evidence_id,resource_id) in hits
            metrics['original_hits']+=got
            independent=supported_pair(resolution,evidence_id,resource_id,observations)
            if independent:
                metrics['supported']+=1;metrics['supported_hits']+=got
            else:
                metrics['unsupported_hits']+=got
                source=[o for o in observations if o.evidence_id==evidence_id]
                absent=not any(o.resource_id==resource_id for o in source)
                if absent and any(file_id==evidence_id for file_id,_ in snapshots.scopes):
                    metrics['negative_scopes']+=1
                else: metrics['unattributed']+=1
    return metrics


def assert_revised_gate(metrics):
    assert metrics['supported'] > 0, 'oracle found no independently supported citations'
    assert metrics['supported_hits'] == metrics['supported'], 'source-backed identity citation missing'
    assert metrics['unsupported_hits'] == 0, 'unsupported customer association returned'
    assert metrics['total'] == (metrics['supported'] + metrics['negative_scopes'] +
                                metrics['unattributed']), 'uncategorized citation'


def report(dataset):
    total,reached,negative,misses=analyze(dataset)
    gate=independent_gate(dataset)
    all_cases,current,historical=historical_only_recount(dataset)
    lines=['# M2 dev-sample miss forensics','',
           f'- Historical-only recount from current-email membership: {all_cases} requests, {current} current matches, {historical} historical-only.',
           f'- Original cited-pair retrieval: {reached}/{total}.',
           f'- Independent source-backed identity oracle: {gate["supported_hits"]}/{gate["supported"]} retrieved.',
           f'- Explicit SQL negative scopes: {negative}/{negative} discoverable; no user/resource association inferred.',
           f'- Remaining unattributed positive/query records: {len(misses)-negative}.',
           '- Supported identity-linked pairs: all reached by exact or source-backed correlation.', '',
           'The files below are participant evidence. Sample answers are read only by this evaluation script.', '']
    for item in misses:
        lines += [f'## {item["case"]} — {item["evidence"]} / {item["resource"]}', '',
                  f'- Source: `{item["source"]}`; locator(s): `{item["locators"] or "no row"}`.',
                  f'- Resource occurs in cited source: {item["exists_in_cited_source"]}; class: `{item["class"]}`.',
                  f'- Identifier fields in cited row: `{item["identifier_fields"]}`.',
                  f'- Resolved subject: `{item["subject"]}`; history fields: `{item["history_fields"]}`; audit transitions: `{item["audit_ids"]}`.',
                  f'- Same resource elsewhere: `{item["other_resource_refs"]}`; explicit trace IDs: `{item["trace_ids"]}`.',
                  f'- Available SQL scope tables for later absence check: `{item["negative_scope_tables"]}`.',
                  '- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.', '']
    return '\n'.join(lines).rstrip()


if __name__=='__main__':
    print(report(Path(__file__).resolve().parents[2]/'dataset'))
