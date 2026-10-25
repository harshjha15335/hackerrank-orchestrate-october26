"""RELAXED (owner-requested experiment): link the subject's account record
through the deletion workflow's own claim rows.

The workflow reports a request as handled at ``reported_at``; the
account_service DELETE_RECORD activity nearest that report (within a window)
is taken as the subject's account. This is a timing/claim join: the row names
no user. It is used only when no record attributes that resource to anyone
else. Absence is then read from the latest complete point-in-time account
snapshot between the activity and ``audit_at`` that has no row for the
resource. No evidence or identifier is invented; the cited snapshot and
activity are real participant files.
"""
from __future__ import annotations

from ingest.evidence import parse_time
from state.engine import StateAssertion, authoritative_sql_scope

WINDOW_SECONDS = 2 * 3600
TABLES = ('customer_profiles_primary', 'customer_profiles_failover_replica')


def claim_activity(request, activity):
    """The account DELETE claim nearest the workflow report, or None."""
    reported = parse_time(request['reported_at'])
    lo, hi = parse_time(request['requested_at']), parse_time(request['audit_at'])
    best = None
    for o in activity:
        raw = o.raw_fields
        if raw.get('target_system') != 'account_service' or raw.get('event_type') != 'DELETE_RECORD':
            continue
        if not o.resource_id or not o.event_time: continue
        when = parse_time(o.event_time)
        if not (lo <= when <= hi): continue
        gap = abs((when - reported).total_seconds())
        if gap <= WINDOW_SECONDS and (best is None or (gap, o.evidence_id) < best[0]):
            best = ((gap, o.evidence_id), o)
    return best[1] if best else None


def claim_owners(requests, activity):
    """Each claim row belongs to at most one request: the one whose report it is
    nearest. A row two requests could claim is never shared."""
    owner = {}
    for request in requests:
        claim = claim_activity(request, activity)
        if claim is None: continue
        gap = abs((parse_time(claim.event_time) - parse_time(request['reported_at'])).total_seconds())
        owner.setdefault(claim.evidence_id, []).append((gap, request['case_id']))
    return {a: min(c)[1] for a, c in owner.items() if len(c) == 1 or sorted(c)[0][0] < sorted(c)[1][0]}


def claim_absences(request, resolution, activity, index, dataset, foreign_owned, owners, has_account):
    if resolution.status != 'resolved' or has_account: return [], None
    claim = claim_activity(request, activity)
    if claim is None or owners.get(claim.evidence_id) != request['case_id'] or foreign_owned(claim.resource_id):
        return [], None
    cutoff, since = parse_time(resolution.audit_at), parse_time(claim.event_time)
    candidates = {}
    for (evidence_id, table), scope in index.scopes.items():
        if table not in TABLES: continue
        when = parse_time(scope.captured_at)
        if since <= when <= cutoff and authoritative_sql_scope(scope, dataset):
            candidates.setdefault(evidence_id, []).append(scope)
    if not candidates: return [], claim
    evidence_id = max(candidates, key=lambda e: (parse_time(candidates[e][0].captured_at), e))
    if any((evidence_id, s.table, claim.resource_id) in index.present for s in candidates[evidence_id]):
        return [], claim
    return [StateAssertion(resolution.case_id, resolution.user_id, 'account_service', claim.resource_id,
                           'customer_profiles', 'ABSENT', evidence_id, f'{s.table}:no-row:{claim.resource_id}',
                           s.captured_at, None, None, s.table, 'direct', 'snapshot', True,
                           f'RELAXED claim link {claim.evidence_id}: complete snapshot omits the account')
            for s in sorted(candidates[evidence_id], key=lambda s: s.table)], claim
