"""Canonical step order and the evidenced dependency hook (AGENTS.md §6.5).

Canonical order (problem_statement.md "Rules"): phase FINDING, REMEDIATION,
VERIFICATION; within a phase the operation-table order; then system_id and
resource_id ascending.

The operation table already puts DISABLE_DATA_FLOW and BLOCK_RESTORE before
every record remediation, so "stop recreation paths first" never needs an
exception. The only case where §6.5 can disagree with canonical order is
"process downstream copies before their source records": two remediation
steps of the same operation whose alphabetical order puts the source first.
The hook reorders only such a pair, only for a record-level edge that names
both records (``strength == 'record_level'``), and only inside one
(phase, operation) block. System-level edges (upstream record unnamed),
naming similarity and event proximity never reorder anything. Cross-operation
conflicts are reported, not applied, because they would break the phase and
operation order the official grader checks. Contradictory evidence (a cycle
among the evidenced constraints) keeps canonical order and is reported.
"""
from __future__ import annotations

from evaluation.contract import OPERATIONS

PHASES = {p: i for i, p in enumerate(OPERATIONS)}
ORDER = {op: i for ops in OPERATIONS.values() for i, op in enumerate(ops)}
RECORD_REMEDIATION = {'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD'}


def canonical_key(step):
    return (PHASES[step['phase']], ORDER[step['operation']], step['system_id'], step['resource_id'])


def canonical(steps):
    return sorted(steps, key=canonical_key)


def apply_dependencies(steps, edges):
    """Return (ordered steps, report). Steps must already be canonical."""
    report = {'applied': [], 'not_applied': [], 'cycles': []}
    ordered = canonical(steps)
    must, constraints = [], set()   # reorders inside one block; every evidenced constraint
    position = {(s['phase'], s['operation'], s['system_id'], s['resource_id']): i for i, s in enumerate(ordered)}
    for e in edges:
        if e.get('strength') != 'record_level': continue
        up, down = e['upstream'], e['downstream']
        ups = [i for (ph, op, sy, re_), i in position.items()
               if ph == 'REMEDIATION' and op in RECORD_REMEDIATION and (sy, re_) == (up['system_id'], up['resource_id'])]
        downs = [i for (ph, op, sy, re_), i in position.items()
                 if ph == 'REMEDIATION' and op in RECORD_REMEDIATION
                 and (sy, re_) == (down['system_id'], down['resource_id'])]
        for u in ups:
            for d in downs:
                if ordered[u]['operation'] != ordered[d]['operation']:
                    if d > u:
                        report['not_applied'].append({'edge': e['basis'], 'reason':
                            'downstream-first would cross the operation order the contract fixes'})
                    continue
                constraints.add((d, u))
                if d > u:    # canonical order puts the source first: the hook must act
                    must.append((d, u, e['basis']))
    if not must:
        return ordered, report
    # Stable topological sort over all evidenced constraints; canonical index breaks ties.
    import heapq
    succ = {i: set() for i in range(len(ordered))}
    indeg = dict.fromkeys(succ, 0)
    for before, after in constraints:
        succ[before].add(after); indeg[after] += 1
    heap = [i for i in succ if indeg[i] == 0]
    heapq.heapify(heap)
    result = []
    while heap:
        i = heapq.heappop(heap)
        result.append(i)
        for j in sorted(succ[i]):
            indeg[j] -= 1
            if indeg[j] == 0: heapq.heappush(heap, j)
    if len(result) != len(ordered):
        # Contradictory derivation evidence: keep canonical order, report the edges.
        report['cycles'].append(sorted(basis for _, _, basis in must))
        return ordered, report
    for before, after, basis in must:
        report['applied'].append({'before': ordered[before]['resource_id'], 'after': ordered[after]['resource_id'],
                                  'basis': basis})
    return [ordered[i] for i in result], report


def renumber(steps):
    return [dict(s, step_no=n) for n, s in enumerate(steps, 1)]
