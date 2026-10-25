"""Citation guard: every nonempty evidence_id must prove its step at audit_at.

The guard does not trust the label an earlier stage attached to a citation. It
re-reads the cited observation (evidence_id + locator) and checks, in order:

1. the ID is a participant-visible file, activity or audit ID;
2. its manifest/event time is at or before the case's audit_at;
3. the observation passes the M4/M5 temporal gate (record and event time not
   after the cutoff or after capture) and is not M1-quarantined;
4. it names the step's resource, belongs to the step's system and describes
   the physical copy (M4 scope) whose state the step relies on;
5. it is not a workflow claim (activity rows, worker results);
6. its own record names the subject and nobody else, or joins an admissible
   same-file trace that does; any foreign identifier rejects it;
7. its re-derived state supports the step's operation and state.

A citation that fails any check is dropped and logged with the reason. The
synthesizer then treats the step's assertion as unproven.
"""
from __future__ import annotations

from dataclasses import dataclass

from flow.engine import attribution
from flow.evidence import admissible, read as read_process
from ingest.evidence import parse_time
from policy.conditions import exposed_fields, identity_claims
from state.engine import (_state_for_observation, authoritative_sql_scope, field_values, physical_scope,
                          system_for, table_system)

from .risk import EXPOSED, read_record

# Re-derived observation states that support each cited operation.
SUPPORTS = {
    # Any materialized record (even one M4 reads as REDACTED) still exists.
    'REPORT_REMAINING_RECORD': {('m4', 'PRESENT'), ('m4', 'REDACTED'), ('m4', 'ANONYMIZED'),
                                ('risk', 'PRESENT'), ('risk', EXPOSED)},
    # A materialized record is checked for exposure field by field below.
    'REPORT_EXPOSED_PII': {('m4', 'PRESENT'), ('m4', 'REDACTED'), ('m4', 'ANONYMIZED'), ('risk', EXPOSED)},
    'REPORT_ACTIVE_DATA_FLOW': {('m6', 'ACTIVE')},
    'REPORT_RESTORE_RISK': {('m6', 'RESTORE_ENABLED')},
    'VERIFY_RECORD_ABSENT': {('m4', 'ABSENT')},
    'VERIFY_RECORD_PRESENT': {('m4', 'PRESENT'), ('m4', 'REDACTED'), ('m4', 'ANONYMIZED')},
    'VERIFY_RECORD_REDACTED': {('m4', 'REDACTED'), ('m4', 'PRESENT')},
    'VERIFY_RECORD_ANONYMIZED': {('m4', 'ANONYMIZED')},
    'VERIFY_DATA_FLOW_DISABLED': {('m6', 'DISABLED')},
    'VERIFY_RESTORE_BLOCKED': {('m6', 'RESTORE_BLOCKED')},
}
# A REDACTED verification on a PRESENT-classified row is valid only when M5
# observed the identifier fields explicitly removed (provenance 'redaction').


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    reason: str


class CitationGuard:
    def __init__(self, observations, context_times, anomalies, fctx, scopes, config=None,
                 snapshots=None, dataset=None):
        self.config = config
        self.by_locator = {(o.evidence_id, o.locator): o for o in observations}
        self.sql_rows = {}
        for o in observations:
            if o.source_type == 'sql' and o.resource_id:
                self.sql_rows.setdefault((o.evidence_id, o.resource_id), []).append(o)
        # F-05: table completeness is re-verified from the snapshot itself.
        self.snapshots = snapshots           # identity.snapshots.SnapshotIndex
        self.dataset = dataset
        self.context_times = context_times   # evidence/activity/audit ID -> datetime
        self.anomalies = frozenset(anomalies)
        self.fctx = fctx
        self.scopes = scopes                 # evidence_id -> set of SQL table names
        self.log = []

    def check(self, case_id, step, provenance, resolution, subject) -> Verdict:
        verdict = self._check(step, provenance, resolution, subject)
        self.log.append({'case_id': case_id, 'operation': step['operation'], 'system_id': step['system_id'],
                         'resource_id': step['resource_id'], 'evidence_id': step['evidence_id'],
                         'locator': (provenance or {}).get('locator'), 'kind': (provenance or {}).get('kind'),
                         'accepted': verdict.accepted, 'reason': verdict.reason})
        return verdict

    def _check(self, step, provenance, resolution, subject) -> Verdict:
        citation = step['evidence_id']
        if not provenance or provenance.get('evidence_id') != citation:
            return Verdict(False, 'no provenance for citation')
        if citation not in self.context_times:
            return Verdict(False, 'unknown participant evidence ID')
        cutoff = parse_time(resolution.audit_at)
        if self.context_times[citation] > cutoff:
            return Verdict(False, 'evidence captured after audit_at')
        locator, kind = provenance['locator'], provenance['kind']
        if kind == 'm4' and ':no-row:' in locator:
            return self._absence(step, locator, citation, provenance, resolution, subject)
        o = self.by_locator.get((citation, locator))
        if o is None:
            return Verdict(False, 'cited locator not found in evidence')
        if o.source_type in ('activity', 'audit'):
            return Verdict(False, 'workflow/activity row is a claim, not proof')
        if not admissible(o, resolution.audit_at, self.anomalies):
            return Verdict(False, 'observation is after the cutoff, after its capture, or quarantined')
        if o.resource_id != step['resource_id']:
            return Verdict(False, 'cited observation does not name the step resource')
        if provenance.get('scope') and physical_scope(o) != provenance['scope']:
            # The citation must describe the physical copy whose state it justifies.
            return Verdict(False, f'cited observation describes copy {physical_scope(o)}, '
                                  f'not {provenance["scope"]}')
        owner_system = system_for(o)
        if kind == 'risk' and o.raw_fields.get('system') == step['system_id']:
            owner_system = step['system_id']   # listing records name their system explicitly
        if owner_system != step['system_id']:
            return Verdict(False, f'cited observation belongs to {owner_system}, not {step["system_id"]}')
        owner = attribution(self.fctx, o, frozenset(identity_claims(o.raw_fields)), subject, resolution.audit_at)
        if owner == 'foreign':
            return Verdict(False, 'cited observation names another person')
        if owner not in ('direct', 'trace') and not provenance.get('m2_correlated'):
            return Verdict(False, 'cited observation is not attributed to the subject')
        if kind == 'm4':
            state, classification, _ = _state_for_observation(o)
            if classification == 'operational_claim':
                return Verdict(False, 'cited observation is an operational claim')
        elif kind == 'm6':
            reading = read_process(o)
            if reading is None or reading.evidence_class in ('claim', 'none'):
                return Verdict(False, 'cited process reading is a claim or stateless')
            state = reading.state
            if state in ('DISABLED', 'RESTORE_BLOCKED') and reading.evidence_class == 'inventory':
                return Verdict(False, 'inventory listing cannot prove a safe process state')
        elif kind == 'risk':
            hit = read_record(o, step['system_id'], step['resource_id'])
            if hit is None or hit[0] != 'risk':
                return Verdict(False, 'cited observation is not a risk-direction reading')
            state = hit[1]
        else:
            return Verdict(False, f'unknown provenance kind {kind}')
        if (kind, state) not in SUPPORTS.get(step['operation'], ()):
            return Verdict(False, f'{kind} state {state} does not support {step["operation"]}')
        if (step['operation'] == 'VERIFY_RECORD_REDACTED' and state == 'PRESENT'
                and not provenance.get('redaction_observed')):
            return Verdict(False, 'identifier removal was not observed in the cited record')
        if step['operation'] == 'VERIFY_RECORD_ANONYMIZED' and not provenance.get('anonymization_proven'):
            # F-02: a row without identifier values is not proof of irreversible unlinking.
            return Verdict(False, 'irreversible anonymization was not evidenced for the cited record')
        if step['operation'] == 'REPORT_EXPOSED_PII' and kind == 'm4':
            permitted = tuple(self.config['permitted_fields'].get(provenance.get('category') or '', ()))
            exposed = exposed_fields(field_values(o.raw_fields), subject, self.config, permitted)
            if not exposed:
                return Verdict(False, 'cited record shows no exposed subject identifier')
        return Verdict(True, f'{kind} {state} via {owner} attribution')

    def _absence(self, step, locator, citation, provenance, resolution, subject) -> Verdict:
        """A point-in-time absence is re-proved, never taken from the caller's table name (F-05).

        The cited table must be the step's physical copy, owned by the step's
        system, admissible at audit_at, a verified complete point-in-time
        snapshot, and must omit a resource that another table of the same
        snapshot independently attributes to the subject.
        """
        table, _, resource = locator.split(':', 2)
        if resource != step['resource_id']:
            return Verdict(False, 'absence scope names another resource')
        if step['operation'] != 'VERIFY_RECORD_ABSENT':
            return Verdict(False, 'table-scope absence supports only VERIFY_RECORD_ABSENT')
        if table not in self.scopes.get(citation, ()):
            return Verdict(False, 'cited snapshot has no such table scope')
        if provenance.get('scope') != table:
            return Verdict(False, f'absence of table {table} does not describe copy {provenance.get("scope")}')
        if table_system(table) != step['system_id']:
            return Verdict(False, f'table {table} does not belong to {step["system_id"]}')
        if any(o.locator.startswith(table + '[') for o in self.sql_rows.get((citation, resource), ())):
            return Verdict(False, 'cited table still contains the resource')
        if self.snapshots is None or self.dataset is None:
            return Verdict(False, 'table completeness cannot be verified')
        scope = self.snapshots.scope(citation, table, resolution.audit_at)
        if scope is None:
            return Verdict(False, 'table scope is not admissible at audit_at')
        if not authoritative_sql_scope(scope, self.dataset):
            return Verdict(False, 'table is not a verified complete point-in-time snapshot')
        references = [o for o in self.sql_rows.get((citation, resource), ())
                      if not o.locator.startswith(table + '[') and system_for(o) == step['system_id']
                      and admissible(o, resolution.audit_at, self.anomalies)
                      and subject.attribution(identity_claims(field_values(o.raw_fields))) == 'SUBJECT']
        if not references:
            return Verdict(False, 'resource is not independently attributed to the subject in this snapshot')
        return Verdict(True, 'complete point-in-time table omits the independently attributed resource')
