"""Risk-direction record readings and referenced source records for M7.

M4 accepts only snapshots, completed readbacks and field values as a record
state, so a record that the owning service itself reports as still indexed,
still downloadable or still carrying a direct identifier stays UNKNOWN. M6
already applies an asymmetric rule to processes: any owned, admissible,
non-claim reading may show risk, but only a source read may prove safety.
This module applies the same rule to records, without changing M4 states or
M5 decisions:

* owning-service telemetry: ``index_query_completed result=hit``, a completed
  ``*_lookup_completed``/``*_query_completed`` with ``rows=1``, an export
  ``available=true`` check, a ``*_pii_scan`` / ``analytics_identity_scan``
  with ``detector=direct_identifier`` and a matched value;
* inventory listings (handover lines, ``record_type``/``result`` records,
  ``record_lookup`` logs) saying FOUND / PRESENT / IDENTIFIABLE;
* an artifact exported by the record's owning system (manifest origin) whose
  document is the record itself.

A reading counts only for a record M2/M4 already link to the subject, only if
its own line names the subject and nobody else at the cutoff (or joins an
admissible same-file trace that does), and only if it passes the M4/M5
temporal gate. NOT_FOUND, ANONYMIZED, ``result=miss`` and ``available=false``
are kept as later "safe-word" readings that cancel an older risk but never
prove compliance. A same-time disagreement cancels too.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from flow.engine import attribution
from flow.evidence import admissible, observed_time, process_kind
from ingest.evidence import parse_time
from policy.conditions import identity_claims
from policy.engine import COMPLIANT, DEFERRED, TEMPLATES, UNRESOLVED, VIOLATION, PolicyDecision, decide_copy
from state.engine import parse_source_bool, system_for

PRESENT, EXPOSED = 'PRESENT', 'EXPOSED'
RISK_WORDS = {'FOUND': PRESENT, 'PRESENT': PRESENT, 'IDENTIFIABLE': EXPOSED}
SAFE_WORDS = {'NOT_FOUND', 'ABSENT', 'DELETED', 'ANONYMIZED', 'REDACTED'}
SCAN_EVENTS = {'message_pii_scan', 'attachment_pii_scan', 'analytics_identity_scan'}
AVAILABILITY_EVENTS = {'export_download_check_completed', 'export_metadata_read_completed'}
# Predicates whose TRUE outcome is exactly "identifiers are still exposed":
# a direct-identifier scan or an IDENTIFIABLE listing is risk-direction proof.
EXPOSURE_PREDICATES = {'still_attributable': EXPOSED, 'contains_email_address': 'EMAIL'}


@dataclass(frozen=True)
class RecordReading:
    evidence_id: str
    locator: str
    observed_at: str
    direction: str       # risk / safe_word
    state: str           # PRESENT / EXPOSED / NOT_RISK
    source: str          # telemetry / inventory / artifact
    basis: str
    attribution: str
    matched_email: bool = False

    def as_dict(self):
        return asdict(self)


def read_record(o, system: str, resource: str):
    """(direction, state, source, basis, matched_email) for one observation, or None."""
    raw = o.raw_fields
    if o.resource_id != resource or o.source_type in ('activity', 'audit'):
        return None
    if (o.source_type == 'log' and raw.get('service') == system and raw.get('resource_id') == resource
            and o.event_time):
        event = raw.get('event')
        if event == 'index_query_completed':
            result = str(raw.get('result', '')).strip().casefold()
            if result == 'hit': return 'risk', PRESENT, 'telemetry', 'owning index reports a hit', False
            if result in ('miss', 'no_hit'): return 'safe_word', 'NOT_RISK', 'telemetry', 'index miss', False
            return None
        if event in SCAN_EVENTS:
            value = raw.get('matched_value')
            if raw.get('detector') == 'direct_identifier' and isinstance(value, str) and value.strip():
                return 'risk', EXPOSED, 'telemetry', f'{event} matched a direct identifier', '@' in value
            return None
        if isinstance(event, str) and event.endswith(('_lookup_completed', '_query_completed')) and 'rows' in raw:
            # A completed lookup by the owning service is a row-count readback
            # that M4's fixed readback vocabulary does not list.
            rows = str(raw.get('rows')).strip()
            if rows == '1': return 'risk', PRESENT, 'telemetry', f'{event} rows=1', False
            if rows == '0': return 'safe_word', 'NOT_RISK', 'telemetry', f'{event} rows=0', False
            return None
        if event in AVAILABILITY_EVENTS:
            available = parse_source_bool(raw.get('available'))
            if available is True: return 'risk', PRESENT, 'telemetry', f'{event} available=true', False
            if available is False: return 'safe_word', 'NOT_RISK', 'telemetry', f'{event} available=false', False
            return None
    if o.source_type in ('txt', 'pdf') and raw.get('system_id') == system:
        word = raw.get('state')
    elif ((o.source_type == 'json' or (o.source_type == 'log' and raw.get('event') == 'record_lookup'))
          and raw.get('system') == system):
        word = raw.get('result')
    elif (o.source_type == 'pdf' and o.locator == f'document:{resource}' and o.source_origin == system
          and system_for(o) == system):
        return 'risk', PRESENT, 'artifact', 'document exported by the owning system is the record', False
    else:
        return None
    if not isinstance(word, str): return None
    word = word.strip().upper()
    if word in RISK_WORDS:
        return 'risk', RISK_WORDS[word], 'inventory', f'listing reports {word}', False
    if word in SAFE_WORDS:
        return 'safe_word', 'NOT_RISK', 'inventory', f'listing reports {word}', False
    return None


def readings(ctx, fctx, system, resource, resolution, subject, extra=()):
    """Owned, admissible readings of one record resource, oldest first."""
    found = []
    seen = set()
    for o in list(ctx.by_resource.get(resource, ())) + list(extra):
        if (o.evidence_id, o.locator) in seen: continue
        seen.add((o.evidence_id, o.locator))
        hit = read_record(o, system, resource)
        if hit is None or not admissible(o, resolution.audit_at, fctx.anomalies): continue
        owner = attribution(fctx, o, frozenset(identity_claims(o.raw_fields)), subject, resolution.audit_at)
        if owner not in ('direct', 'trace'): continue
        direction, state, source, basis, email = hit
        found.append(RecordReading(o.evidence_id, o.locator, observed_time(o), direction, state, source,
                                   basis, owner, email))
    return sorted(found, key=lambda r: (parse_time(r.observed_at), r.evidence_id, r.locator))


def latest_risk(found):
    """The latest reading if it is risk and nothing at the same time disagrees."""
    if not found: return None
    last = found[-1]
    tied = {r.direction for r in found if parse_time(r.observed_at) == parse_time(last.observed_at)}
    if last.direction != 'risk' or len(tied) > 1: return None
    # The strongest state among same-time risk readings (exposure implies presence).
    same = [r for r in found if parse_time(r.observed_at) == parse_time(last.observed_at)]
    return max(same, key=lambda r: (r.state == EXPOSED, r.matched_email, r.evidence_id, r.locator))


def _predicate(ctx, rule_id):
    rule = next((r for r in ctx.table.rules if r.rule_id == rule_id), None)
    if rule is None or rule.unconditional: return None
    binding = ctx.config['bindings'].get(rule.condition_fingerprint)
    return binding['predicate'] if binding else None


def _later_safe_fact(decisions, risk):
    """Another physical copy observed safe after the risk reading keeps the risk stale."""
    point = parse_time(risk.observed_at)
    for d in decisions:
        if d['state_supported'] and d['observed_state'] in ('ABSENT', 'REDACTED', 'ANONYMIZED'):
            # M4 captured_at is the latest possible time the safe state held.
            if d.get('_observed_at') and parse_time(d['_observed_at']) > point:
                return True
    return False


def overlay(ctx, fctx, policy, resolution, subject, observed_at):
    """Return (decisions, notes): M5 copy decisions with risk readings applied.

    Only UNRESOLVED copies whose M4 state is UNKNOWN can change, and only to
    VIOLATION. Each change keeps the risk reading as provenance.
    """
    out, notes = [], []
    groups = {}
    for d in policy['decisions']:
        groups.setdefault((d['system_id'], d['resource_id']), []).append(dict(d, _observed_at=observed_at.get(
            (d['evidence_id'], d['locator']))))
    for (system, resource), copies in sorted(groups.items(), key=lambda kv: (kv[0][0] or '', kv[0][1] or '')):
        if not system or not resource or process_kind(system, resource):
            out.extend(copies); continue
        found = readings(ctx, fctx, system, resource, resolution, subject)
        risk = latest_risk(found)
        for d in copies:
            new = d
            if (risk and d['compliance'] == UNRESOLVED and d['observed_state'] == 'UNKNOWN'
                    and not d['attribution_conflicts'] and not _later_safe_fact(copies, risk)):
                action, why = None, None
                if d['effective_action'] and d['condition_outcome'] in ('TRUE', 'FALSE'):
                    action = d['effective_action']
                elif d['condition_outcome'] == 'UNKNOWN' and d['rule_id']:
                    need = EXPOSURE_PREDICATES.get(_predicate(ctx, d['rule_id']))
                    if need == EXPOSED and risk.state == EXPOSED or need == 'EMAIL' and risk.matched_email:
                        action, why = d['required_action'], f'condition TRUE by {risk.source} exposure reading'
                if action == 'DELETE' or (action in ('REDACT', 'ANONYMIZE') and risk.state == EXPOSED):
                    new = dict(d, compliance=VIOLATION, effective_action=action,
                               condition_outcome='TRUE' if why else d['condition_outcome'],
                               condition_reason=why or d['condition_reason'],
                               obligations=TEMPLATES[action],
                               reason=f'M7 risk reading {risk.evidence_id}:{risk.locator} ({risk.source}): {risk.basis}',
                               _risk=risk.as_dict())
                    notes.append({'system_id': system, 'resource_id': resource, 'topology': d['topology'],
                                  'from': d['reason'], 'to': VIOLATION, 'action': action, 'reading': risk.as_dict()})
            if found and not new.get('_risk'):
                new = dict(new, _readings=[r.as_dict() for r in found])
            out.append(new)
    return out, notes


def rollup(decisions):
    """M5's worst-copy rollup over (possibly overlaid) decision dicts."""
    from policy.engine import rollup as m5_rollup
    fields = set(PolicyDecision.__dataclass_fields__)
    objects, extras = [], {}
    for d in decisions:
        obj = PolicyDecision(**{k: v for k, v in d.items() if k in fields})
        objects.append(obj)
        extras[id(obj)] = d
    resources = m5_rollup(objects)
    for r in resources:
        copies = [extras[id(o)] for o in objects if (o.system_id or '', o.resource_id or '') ==
                  (r['system_id'], r['resource_id'])]
        r['copy_decisions'] = copies
        worst = next((c for c in copies if c['evidence_id'] == r['deciding_copy']['evidence_id']
                      and c['topology'] == r['deciding_copy']['topology']
                      and c['locator'] == r['deciding_copy']['locator']), None)
        r['deciding_copy'] = dict(r['deciding_copy'], risk=(worst or {}).get('_risk'))
    return resources


def referenced_sources(ctx, fctx, policy, resolution, subject, activity_systems):
    """Records named as the source of a subject-attributed record.

    A record that names only the subject and carries ``source_resource_id``
    states which record it was derived from. That upstream record is the
    subject's too. Its system comes from participant activity rows naming the
    resource (all admissible rows must agree); otherwise it is not added.
    Returns (new M5 copy decisions with UNKNOWN state, record-level edges).
    """
    linked = {(d['system_id'], d['resource_id']) for d in policy['decisions']}
    decisions, edges, seen = [], [], set()
    for d in policy['decisions']:
        o = ctx.by_locator.get((d['evidence_id'], d['locator']))
        if o is None or d['attribution_conflicts']: continue
        source = o.raw_fields.get('source_resource_id')
        if not isinstance(source, str) or not source.strip(): continue
        if subject.attribution(identity_claims(o.raw_fields)) != 'SUBJECT': continue
        if not admissible(o, resolution.audit_at, fctx.anomalies): continue
        systems = {row.raw_fields.get('target_system') for row in activity_systems.get(source, ())
                   if admissible(row, resolution.audit_at, fctx.anomalies)}
        if len(systems) != 1 or None in systems: continue
        system = systems.pop()
        edges.append({'kind': 'derived_from_record', 'strength': 'record_level',
                      'upstream': {'system_id': system, 'resource_id': source},
                      'downstream': {'system_id': d['system_id'], 'resource_id': d['resource_id']},
                      'evidence_id': o.evidence_id, 'locator': o.locator,
                      'basis': f'{o.evidence_id}:{o.locator} source_resource_id={source}'})
        if (system, source) in linked or (system, source) in seen: continue
        seen.add((system, source))
        latest = {'system_id': system, 'resource_id': source, 'topology': 'service', 'state': 'UNKNOWN',
                  'supported': False, 'explanation': 'named as source by a subject record; state not observed',
                  'evidence_id': o.evidence_id, 'locator': o.locator}
        decision = decide_copy(ctx, latest, [], resolution, subject).as_dict()
        decisions.append(dict(decision, _referenced_by=f'{o.evidence_id}:{o.locator}'))
    return decisions, edges
