"""Inspect identity and evidence references for one case; no audit decision."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from ingest.evidence import ingest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[2] / 'dataset')
    args = parser.parse_args()
    graph = IdentityGraph(args.dataset)
    case = next((r for r in graph.requests(args.sample) if r['case_id'] == args.case), None)
    if case is None: parser.error('case_id not found in selected request file')
    resolution = graph.resolve(case)
    observations, _, _ = ingest(args.dataset)
    hits = EvidenceIndex(observations, graph=graph).find(resolution)
    print(json.dumps({'case_id': case['case_id'], 'resolution': asdict(resolution),
                      'evidence': [{'evidence_id': h.observation.evidence_id,
                                    'locator': h.observation.locator,
                                    'resource_id': h.observation.resource_id,
                                    'system_id': h.observation.system_id,
                                    'source_path': h.observation.source_path,
                                    'captured_at': h.observation.captured_at,
                                    'strength': h.strength, 'matched': h.matched}
                                   for h in hits]}, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__': main()
