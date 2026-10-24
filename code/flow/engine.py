"""M6 active data-flow and restore-path assessments at a case's audit_at.

For every process resource (integration_service data_flow_*, backup_service
backup_*) that participant evidence ties to the deletion subject, the engine
selects the latest admissible, subject-attributed reading and maps it to an
assessment and obligation template. It never writes steps_json, orders steps
or cites evidence for remediation: those belong to M7.

Ownership: a reading counts only if the record itself names the subject and
nobody else at the cutoff (direct), or if it carries no identifier and shares
an explicit trace ID with lines that name only the subject (trace). A shared
resource ID, file, event stream or name similarity is never ownership. A
same-ID reading that names another person makes ownership contested, so the
assessment is CONFLICTING.

Safety asymmetry: risk (ACTIVE / RESTORE_ENABLED) may be shown by any
non-claim reading; a safe state (DISABLED / RESTORE_BLOCKED) is accepted only
from a snapshot, completed readback or observed configuration fields. UNKNOWN
and CONFLICTING never imply safety.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from ingest.evidence import Observation, parse_time
from policy.conditions import Subject, identity_claims, subject_from
from state.engine import field_values

from .evidence import (FLOW, RELIABILITY, RESTORE, RISK, SAFE, SAFE_PROOF, Reading,
                       admissible, observation_kind, read)

ACTIVE, DISABLED, ENABLED, BLOCKED = 'ACTIVE', 'DISABLED', 'RESTORE_ENABLED', 'RESTORE_BLOCKED'
UNKNOWN, CONFLICTING = 'UNKNOWN', 'CONFLICTING'
# Problem-statement operation table; FINDING cites observed evidence, the rest
# are proposed future work (empty evidence for an INCOMPLETE case).
TEMPLATES = {
    ACTIVE: (('FINDING', 'REPORT_ACTIVE_DATA_FLOW', 'ACTIVE'),
             ('REMEDIATION', 'DISABLE_DATA_FLOW', 'DISABLED'),
             ('VERIFICATION', 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED')),
    DISABLED: (('VERIFICATION', 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED'),),
    ENABLED: (('FINDING', 'REPORT_RESTORE_RISK', 'ACTIVE'),
              ('REMEDIATION', 'BLOCK_RESTORE', 'BLOCKED'),
              ('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED')),
    BLOCKED: (('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED'),),
}


@dataclass(frozen=True)
class Assessment:
    case_id: str
    user_id: str | None
    kind: str
    system_id: str
    resource_id: str
    status: str
    supported: bool
    reason: str
    deciding: dict | None
    attribution: str | None
    carry_basis: str | None
    obligations: tuple[dict, ...]
    readings: tuple[dict, ...]
    claims: tuple[dict, ...]
    ownership_conflicts: tuple[str, ...]
    unattributed_same_id: tuple[str, ...]
    later_unverified_claims: tuple[str, ...]

    def as_dict(self):
        return asdict(self)


class FlowContext:
    """Case-independent indexes over M1 observations for process resources."""

    def __init__(self, observations: list[Observation], anomalies=frozenset()):
        self.anomalies = frozenset(anomalies)
        self.process = defaultdict(list)   # (system, resource) -> [(observation, reading, claims)]
        self.activity = []                  # activity rows for dependency evidence
        traces = defaultdict(list)
        for o in observations:
            if o.source_type == 'activity':
                self.activity.append(o)
            if o.source_type == 'log' and o.raw_fields.get('trace_id'):
                traces[(o.evidence_id, o.raw_fields['trace_id'])].append(o)
            kind = observation_kind(o)
            if kind is None: continue
            reading = read(o)
            if reading is None: continue
            system = o.raw_fields.get('target_system') if o.source_type == 'activity' else o.system_id
            self.process[(system, o.resource_id)].append((o, reading, _claims(o)))
        # Same-file trace groups with each line's identifiers. Which lines may
        # act as identity anchors depends on the case cutoff (trace_identity).
        self.traces = {key: tuple((o, _claims(o)) for o in group) for key, group in traces.items()}
        self.destinations = {}
        for (system, resource), items in self.process.items():
            for o, _, _ in items:
                target = field_values(o.raw_fields).get('destination')
                if isinstance(target, str) and target:
                    self.destinations.setdefault((system, resource), set()).add((target, o.evidence_id, o.locator))


def _claims(o: Observation) -> frozenset:
    return frozenset(identity_claims(o.raw_fields))


def trace_identity(fctx: FlowContext, o: Observation, cutoff: str) -> frozenset:
    """Identifiers named by the admissible lines of o's exact same-file trace.

    An anchor captured, emitted or recorded after the cutoff (or after its own
    capture), or quarantined by M1, is not evidence at the cutoff: it can
    neither establish nor contest ownership of another line in the trace.
    """
    trace = o.raw_fields.get('trace_id') if o.source_type == 'log' else None
    group = fctx.traces.get((o.evidence_id, trace), ()) if trace else ()
    return frozenset().union(*(claims for line, claims in group
                               if admissible(line, cutoff, fctx.anomalies)))


def attribution(fctx: FlowContext, o: Observation, claims, subject: Subject, cutoff: str) -> str:
    """direct / trace / foreign / none for one reading's own record."""
    verdict = subject.attribution(claims)
    if verdict == 'SUBJECT': return 'direct'
    if verdict == 'FOREIGN': return 'foreign'
    if subject.attribution(trace_identity(fctx, o, cutoff)) == 'SUBJECT':
        return 'trace'
    return 'none'


def _order(r: Reading):
    return (parse_time(r.observed_at), RELIABILITY[r.evidence_class], r.evidence_id, r.locator)


def _carry(kind, deciding_attr, o: Observation | None) -> str | None:
    if o is None: return None
    noun = 'connector' if kind == FLOW else 'archive entry'
    if deciding_attr == 'direct':
        return f'{noun} record names the subject ({o.evidence_id}:{o.locator})'
    return f'{noun} reported inside a trace keyed only by the subject ({o.evidence_id}:{o.locator})'


def obligations(status: str, deciding: Reading | None) -> tuple[dict, ...]:
    if status not in TEMPLATES: return ()
    out = []
    for phase, operation, state in TEMPLATES[status]:
        observed = phase == 'FINDING' or len(TEMPLATES[status]) == 1
        out.append({'phase': phase, 'operation': operation, 'state': state,
                    'basis': 'observed' if observed else 'proposed',
                    'evidence_id': deciding.evidence_id if observed and deciding else ''})
    return tuple(out)


def assess(fctx: FlowContext, key, resolution, subject: Subject) -> Assessment | None:
    system, resource = key
    items = fctx.process.get(key, ())
    if not items: return None
    kind = observation_kind(items[0][0])
    cutoff = resolution.audit_at
    used, readings, claims, conflicts, unattributed, owned = [], [], [], [], [], False
    for o, reading, record_claims in sorted(items, key=lambda i: (i[1].evidence_id, i[1].locator)):
        ok_time = admissible(o, cutoff, fctx.anomalies)
        if o.source_type == 'activity':
            # Activity rows carry no subject identifier; they are claims only.
            if ok_time: claims.append(reading.as_dict())
            continue
        attr = attribution(fctx, o, record_claims, subject, cutoff)
        entry = dict(reading.as_dict(), attribution=attr, admissible=ok_time)
        readings.append(entry)
        if not ok_time: continue
        if attr in ('direct', 'trace'):
            owned = True
            if reading.state != UNKNOWN and reading.evidence_class != 'claim':
                used.append((reading, attr, o))
        elif attr == 'foreign':
            conflicts.append(f'{o.evidence_id}:{o.locator}')
        else:
            unattributed.append(f'{o.evidence_id}:{o.locator}')
    if not owned:
        return None
    base = dict(case_id=resolution.case_id, user_id=resolution.user_id, kind=kind, system_id=system,
                resource_id=resource, readings=tuple(readings), claims=tuple(claims),
                ownership_conflicts=tuple(conflicts), unattributed_same_id=tuple(unattributed))
    if not used:
        return Assessment(**base, status=UNKNOWN, supported=False, deciding=None, attribution=None,
                          carry_basis=None, obligations=(), later_unverified_claims=(),
                          reason='subject-linked process has no admissible verified state')
    used.sort(key=lambda u: _order(u[0]))
    latest, attr, source = used[-1]
    later = tuple(sorted(f'{c["evidence_id"]}:{c["claimed"]}' for c in claims
                         if c['claimed'] and parse_time(c['observed_at']) > parse_time(latest.observed_at)))
    tied = sorted({u[0].state for u in used
                   if parse_time(u[0].observed_at) == parse_time(latest.observed_at)})
    deciding = dict(latest.as_dict(), attribution=attr)
    common = dict(base, deciding=deciding, attribution=attr, carry_basis=_carry(kind, attr, source),
                  later_unverified_claims=later)
    if conflicts:
        return Assessment(**common, status=CONFLICTING, supported=False, obligations=(),
                          reason='same resource ID names another person: ' + ', '.join(conflicts))
    if len(tied) > 1:
        return Assessment(**common, status=CONFLICTING, supported=False, obligations=(),
                          reason='readings at the same observation time disagree: ' + ','.join(tied))
    if latest.state == SAFE[kind] and latest.evidence_class not in SAFE_PROOF:
        return Assessment(**common, status=UNKNOWN, supported=False, obligations=(),
                          reason=f'latest reading is {latest.state} only by {latest.evidence_class}; '
                                 'a safe state needs a snapshot, readback, observed configuration or owning-service status')
    reason = (f'latest admissible reading {latest.evidence_id}:{latest.locator} '
              f'({latest.evidence_class}) shows {latest.state}')
    return Assessment(**common, status=latest.state, supported=True, reason=reason,
                      obligations=obligations(latest.state, latest))


def assess_case(fctx: FlowContext, resolution) -> list[Assessment]:
    if resolution.status != 'resolved' or not resolution.user_id: return []
    subject = subject_from(resolution)
    out = []
    for key in sorted(k for k in fctx.process if k[0] and k[1]):
        found = assess(fctx, key, resolution, subject)
        if found: out.append(found)
    return out
