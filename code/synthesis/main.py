"""M7 inference: decisions and steps_json for every request, from participant data only.

    python3 code/synthesis/main.py --output /tmp/m7/predictions.csv          # 518 cases
    python3 code/synthesis/main.py --sample --output /tmp/m7/sample.csv      # 32 samples
    python3 code/synthesis/main.py --sample --case <case_id> --explain       # one case, JSON

The root output.csv and dataset/ are protected until the final submission
stage (M10). Nothing here reads the public sample answers. No network or model calls:
M3 intent runs in its offline rules mode, and M8 screenshot evidence comes from
the committed manual fixtures (``--no-visual`` runs the M7 ablation baseline).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.contract import COLUMNS, load_context, timestamp
from flow.dependencies import build as build_edges, index_activity, precedence
from flow.engine import FlowContext, assess_case
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest.evidence import ingest
from intent.classifier import IntentClassifier
from policy.conditions import subject_from
from policy.engine import Context, decide_case
from state.engine import reconstruct

from synthesis.citations import CitationGuard
from synthesis.risk import overlay, referenced_sources, rollup
from synthesis.synthesizer import synthesize
from vision.adapter import QUARANTINE_REASONS, load as load_visual

ROOT = Path(__file__).resolve().parents[2]


class Pipeline:
    """M1–M6 contexts built once; ``case`` runs M2→M7 for one request."""

    def __init__(self, dataset: Path, sample=False, cache: Path | None = None, visual=True,
                 vision_cache: Path | None = None):
        self.dataset = Path(dataset)
        self.sample = sample
        self.graph = IdentityGraph(self.dataset)
        observations, coverage, discrepancies = ingest(self.dataset, cache)
        # M8: screenshot records join the M1 table and pass through every later stage.
        self.visual = load_visual(self.dataset, vision_cache) if visual else None
        if self.visual:
            observations = observations + self.visual.observations
            discrepancies = discrepancies + self.visual.discrepancies
        self.anomalies = {(d['file_id'], d['locator']) for d in discrepancies
                          if d['reason'] in QUARANTINE_REASONS}
        self.evidence = EvidenceIndex(observations, self.anomalies)
        self.scopes = SnapshotIndex(observations, coverage)
        self.ctx = Context(observations, self.dataset / 'deletion_rules.csv', anomalies=self.anomalies)
        self.fctx = FlowContext(observations, self.anomalies)
        self.indexes = index_activity(self.fctx.activity)
        self.classifier = IntentClassifier()
        self.activity_by_resource = defaultdict(list)
        for o in self.fctx.activity:
            if o.resource_id: self.activity_by_resource[o.resource_id].append(o)
        _, times = load_context(self.dataset, 'sample' if sample else 'full')
        tables = defaultdict(set)
        for c in coverage:
            tables[c['file_id']].update((c.get('tables') or {}).keys())
        self.guard = CitationGuard(observations, times, self.anomalies, self.fctx, tables, self.ctx.config)

    def requests(self):
        return sorted(self.graph.requests(self.sample), key=lambda r: r['case_id'])

    def case(self, request):
        resolution = self.graph.resolve(request)
        intent = self.classifier.classify(request['request_text']).intent
        view = {'case_id': request['case_id'], 'intent': intent, 'flows': [], 'restores': [], 'resources': []}
        if resolution.status != 'resolved':
            return synthesize(view, self.guard, resolution, None) + ({'resolution': resolution.status},)
        subject = subject_from(resolution)
        state = reconstruct(resolution, self.evidence.find(resolution), self.scopes, self.dataset, self.anomalies)
        policy = decide_case(self.ctx, state, resolution)
        assessments = assess_case(self.fctx, resolution)
        timing, strength = {}, {}
        for a in state['latest']:
            timing[(a['evidence_id'], a['locator'])] = a['event_time'] or a['record_time'] or a['captured_at']
            strength[(a['evidence_id'], a['locator'])] = a['attribution']
        extra, record_edges = referenced_sources(self.ctx, self.fctx, policy, resolution, subject,
                                                 self.activity_by_resource)
        policy = dict(policy, decisions=policy['decisions'] + extra)
        decisions, risk_notes = overlay(self.ctx, self.fctx, policy, resolution, subject, timing)
        for d in decisions:
            d['_attribution'] = strength.get((d['evidence_id'], d['locator']))
        resources = rollup(decisions)
        edges = build_edges(self.fctx, self.indexes, resolution, assessments, resources, decisions)
        view.update(flows=[a.as_dict() for a in assessments if a.kind == 'DATA_FLOW'],
                    restores=[a.as_dict() for a in assessments if a.kind == 'RESTORE_PATH'],
                    resources=resources)
        row, diagnostics = synthesize(view, self.guard, resolution, subject, list(edges) + record_edges)
        diagnostics.update(risk_overlay=risk_notes, referenced_sources=[e['basis'] for e in record_edges],
                           record_edges=record_edges,
                           process_precedence=len(precedence(assessments, resources, edges)),
                           m4_unknown_latest=sum(not a['supported'] for a in state['latest']))
        return row, diagnostics, {'resolution': resolution.status, 'user_id': resolution.user_id}


def run(dataset: Path, sample=False, cache: Path | None = None, visual=True, vision_cache: Path | None = None):
    pipeline = Pipeline(dataset, sample, cache, visual, vision_cache)
    rows, diagnostics = [], {}
    for request in pipeline.requests():
        row, diag, meta = pipeline.case(request)
        rows.append(row)
        diagnostics[row['case_id']] = dict(diag, **meta)
    return rows, diagnostics, pipeline


def serialize(rows) -> str:
    """Deterministic CSV text; steps use the contract's field order, compact JSON."""
    import io
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(COLUMNS)
    order = ('step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id')
    for row in sorted(rows, key=lambda r: r['case_id']):
        steps = [{k: s[k] for k in order} for s in row['steps_json']]
        writer.writerow((row['case_id'], row['deletion_status'],
                         json.dumps(steps, ensure_ascii=False, separators=(',', ':'))))
    return buffer.getvalue()


def protected(path: Path) -> bool:
    path = path.resolve()
    return path == (ROOT / 'output.csv').resolve() or path.is_relative_to((ROOT / 'dataset').resolve())


def summary(rows, diagnostics, guard):
    status = Counter(r['deletion_status'] for r in rows)
    log = guard.log
    return {'cases': len(rows), 'status': dict(sorted(status.items())),
            'steps': sum(len(r['steps_json']) for r in rows),
            'operations': dict(sorted(Counter(s['operation'] for r in rows for s in r['steps_json']).items())),
            'citations_checked': len(log), 'citations_accepted': sum(e['accepted'] for e in log),
            'citations_rejected': sum(not e['accepted'] for e in log),
            'rejection_reasons': dict(sorted(Counter(e['reason'] for e in log if not e['accepted']).items())),
            'incomplete_without_findings': sum(1 for r in rows if r['deletion_status'] == 'INCOMPLETE'
                                               and not any(s['phase'] == 'FINDING' for s in r['steps_json'])),
            'incomplete_empty': sum(1 for r in rows if r['deletion_status'] == 'INCOMPLETE' and not r['steps_json']),
            'unresolved_items': sum(len(d.get('unresolved', ())) for d in diagnostics.values()),
            'cases_with_unresolved': sum(bool(d.get('unresolved')) for d in diagnostics.values()),
            'risk_overlay_copies': sum(n['to'] == 'VIOLATION' for d in diagnostics.values()
                                       for n in d.get('risk_overlay', ())),
            'risk_overlay_unapplied': sum(n['to'] is None for d in diagnostics.values()
                                          for n in d.get('risk_overlay', ())),
            'referenced_sources': sum(len(d.get('referenced_sources', ())) for d in diagnostics.values()),
            'dependency_reorders': sum(len((d.get('dependency_report') or {}).get('applied', ()))
                                       for d in diagnostics.values()),
            'dependency_not_applied': sum(len((d.get('dependency_report') or {}).get('not_applied', ()))
                                          for d in diagnostics.values()),
            'dependency_cycles': sum(len((d.get('dependency_report') or {}).get('cycles', ()))
                                     for d in diagnostics.values()),
            'm4_unknown_latest': sum(d.get('m4_unknown_latest', 0) for d in diagnostics.values())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--sample', action='store_true', help='the 32 public sample requests')
    parser.add_argument('--output', type=Path, help='temporary evaluation CSV (never root output.csv)')
    parser.add_argument('--case', help='inspect one case')
    parser.add_argument('--explain', action='store_true', help='print diagnostics for --case')
    parser.add_argument('--summary', action='store_true', help='print aggregate counts')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/m4-ingest-cache'))
    parser.add_argument('--no-visual', action='store_true', help='ablation: leave M8 screenshot evidence out')
    parser.add_argument('--vision-cache', type=Path, help='content-addressed M8 extraction cache')
    args = parser.parse_args(argv)
    if args.output and protected(args.output):
        parser.error('M7 writes only to a temporary evaluation path; root output.csv and dataset/ are protected')
    rows, diagnostics, pipeline = run(args.dataset, args.sample, args.cache, not args.no_visual, args.vision_cache)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialize(rows), encoding='utf-8')
    if args.case:
        row = next((r for r in rows if r['case_id'] == args.case), None)
        if row is None: parser.error('case ID not found')
        result = {'row': row}
        if args.explain:
            result['diagnostics'] = diagnostics[args.case]
            result['citations'] = [e for e in pipeline.guard.log if e['case_id'] == args.case]
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, default=str))
    elif args.summary or not args.output:
        print(json.dumps(summary(rows, diagnostics, pipeline.guard), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
