"""Evidenced dependencies between processes and subject-linked records, for M7.

Edges come only from explicit evidence: a recreation event that names both a
subject-attributed process and the downstream record it repopulated, a
derivation event whose target is a subject-linked record, a connector's
configured destination field, or the same resource observed in several
physical topologies. An upstream that the
evidence does not name stays unnamed (resource_id None): no connector, backup
or source record is inferred from naming similarity, event proximity or the
case's other resources. Activity rows are claims that an event ran; they order
work but never prove a state. This module recommends; M7 orders steps.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .evidence import admissible

# Recreation events name the process as resource_id and the downstream record
# in details; derivation events name only the downstream record.
RECREATION = {('SYNC_RECORD', 'integration_service'): 'recreated_by_sync',
              ('RESTORE_BACKUP', 'backup_service'): 'recreated_by_restore'}
DERIVATION = {('INDEX_RECORD', 'account_service'), ('SYNC_RECORD', 'account_service'),
              ('REFRESH_CACHE', 'account_service'), ('UPDATE_RECORD', 'support_platform')}
DOWNSTREAM = re.compile(r'downstream resource ([a-z]+(?:_[a-z]+)*_\d+)\b')
REMEDIATION = {'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD'}
PROCESS_FIRST = {'DISABLE_DATA_FLOW', 'BLOCK_RESTORE'}


def index_activity(rows):
    """Return (by upstream process, by derived downstream record) activity indexes."""
    by_process, by_target = defaultdict(list), defaultdict(list)
    for o in rows:
        raw = o.raw_fields
        key = (raw.get('event_type'), raw.get('source_system'))
        if key in RECREATION and o.resource_id:
            found = DOWNSTREAM.search(str(raw.get('details', '')))
            if found:
                by_process[(raw['source_system'], o.resource_id)].append(
                    (RECREATION[key], (raw.get('target_system'), found.group(1)), o))
        elif key in DERIVATION and o.resource_id:
            by_target[(raw.get('target_system'), o.resource_id)].append(('derived_from_source_system', o))
    return by_process, by_target


def build(fctx, indexes, resolution, assessments, resources, decisions):
    by_process, by_target = indexes
    cutoff = resolution.audit_at
    linked = sorted({(r['system_id'], r['resource_id']) for r in resources if r['system_id'] and r['resource_id']})
    edges = []
    for a in assessments:
        for kind, downstream, o in sorted(by_process.get((a.system_id, a.resource_id), ()),
                                          key=lambda item: item[2].evidence_id):
            if not admissible(o, cutoff, fctx.anomalies): continue
            edges.append({'kind': kind, 'upstream': {'system_id': a.system_id, 'resource_id': a.resource_id},
                          'downstream': {'system_id': downstream[0], 'resource_id': downstream[1]},
                          'downstream_subject_linked': downstream in linked,
                          'evidence_id': o.evidence_id, 'evidence_class': 'activity_claim',
                          'reported_result': o.raw_fields.get('reported_result'), 'event_time': o.event_time})
    for target in linked:
        for kind, o in sorted(by_target.get(target, ()), key=lambda item: item[1].evidence_id):
            if not admissible(o, cutoff, fctx.anomalies): continue
            raw = o.raw_fields
            edges.append({'kind': kind, 'upstream': {'system_id': raw['source_system'], 'resource_id': None},
                          'downstream': {'system_id': target[0], 'resource_id': target[1]},
                          'evidence_id': o.evidence_id, 'evidence_class': 'activity_claim',
                          'reported_result': raw.get('reported_result'), 'event_time': o.event_time,
                          'note': 'upstream record is not named by the evidence'})
    for a in assessments:
        for target, evidence_id, locator in sorted(fctx.destinations.get((a.system_id, a.resource_id), ())):
            o = next((o for o, _, _ in fctx.process[(a.system_id, a.resource_id)]
                      if (o.evidence_id, o.locator) == (evidence_id, locator)), None)
            if o is None or not admissible(o, cutoff, fctx.anomalies): continue
            edges.append({'kind': 'flow_destination',
                          'upstream': {'system_id': a.system_id, 'resource_id': a.resource_id},
                          'downstream': {'system_id': None, 'store': target},
                          'evidence_id': evidence_id, 'evidence_class': 'configuration', 'locator': locator})
    copies = defaultdict(list)
    for d in decisions:
        if d['system_id'] and d['resource_id']:
            copies[(d['system_id'], d['resource_id'])].append(d)
    for (system, resource), group in sorted(copies.items()):
        topologies = sorted({d['topology'] or 'service' for d in group})
        if len(topologies) > 1:
            edges.append({'kind': 'physical_copies', 'upstream': {'system_id': system, 'resource_id': resource},
                          'downstream': {'system_id': system, 'resource_id': resource, 'topologies': topologies},
                          'evidence_id': ','.join(sorted({d['evidence_id'] for d in group})),
                          'evidence_class': 'observed_copies'})
    return edges


def precedence(assessments, resources, edges):
    """Recommended (not final) ordering constraints for M7.

    Every supported active flow or enabled restore path must be stopped before
    any record remediation in the case (AGENTS.md §6.5). A downstream copy
    with an evidenced derivation edge is recommended before records of its
    named upstream system; that edge is system-level because the upstream
    record is not named.
    """
    process = [{'system_id': a.system_id, 'resource_id': a.resource_id, 'operation': o['operation']}
               for a in assessments for o in a.obligations if o['operation'] in PROCESS_FIRST]
    records = sorted({(r['system_id'], r['resource_id'], op) for r in resources
                      for _, op, _ in r.get('obligations', ()) if op in REMEDIATION})
    rules = []
    for p in process:
        for system, resource, op in records:
            rules.append({'before': p, 'after': {'system_id': system, 'resource_id': resource, 'operation': op},
                          'basis': 'stop recreation paths before dependent record remediation',
                          'strength': 'contract_rule'})
    for e in edges:
        if not e['kind'].startswith('derived_from'): continue
        down = (e['downstream']['system_id'], e['downstream']['resource_id'])
        for system, resource, op in records:
            if system == e['upstream']['system_id'] and (system, resource) != down:
                for dsys, dres, dop in records:
                    if (dsys, dres) == down:
                        rules.append({'before': {'system_id': dsys, 'resource_id': dres, 'operation': dop},
                                      'after': {'system_id': system, 'resource_id': resource, 'operation': op},
                                      'basis': f'{e["kind"]} {e["evidence_id"]}: downstream copy before source system',
                                      # The upstream record is not named: M7 decides whether
                                      # a system-level edge may reorder steps.
                                      'strength': 'system_level'})
    unique = {repr(sorted((k, sorted(v.items()) if isinstance(v, dict) else v) for k, v in r.items())): r for r in rules}
    return [unique[k] for k in sorted(unique)]
