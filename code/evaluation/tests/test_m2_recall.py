"""Public sample answers are used only in evaluation tests, never retrieval code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.contract import read_output
from identity.graph import IdentityGraph
from identity.retrieval import EvidenceIndex
from ingest.evidence import ingest

DATASET = Path(__file__).resolve().parents[3] / 'dataset'


def test_dev_sample_reachability_is_measured_without_inventing_links():
    graph = IdentityGraph(DATASET)
    observations, _, _ = ingest(DATASET)
    index = EvidenceIndex(observations)
    gold = {row['case_id']: row for row in read_output(DATASET / 'sample_output.csv')}
    requests = sorted(graph.requests(sample=True), key=lambda r: r['case_id'])[:22]
    reached = total = 0
    missing = []
    for case in requests:
        found = {(h.observation.evidence_id, h.observation.resource_id)
                 for h in index.find(graph.resolve(case))}
        for step in gold[case['case_id']]['steps_json']:
            if not step['evidence_id']: continue
            total += 1
            if (step['evidence_id'], step['resource_id']) in found: reached += 1
            else: missing.append((case['case_id'], step['evidence_id'], step['resource_id']))
    assert total == 38 and reached == 31 and len(missing) == 7
    # This is a characterization test of a known unmet M2-4 gate. Do not
    # loosen retrieval's identity standard just to increase this score.
