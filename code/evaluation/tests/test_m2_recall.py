"""Measure public dev citations only in evaluation; do not encode a miss as success."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.m2_forensics import analyze, report

DATASET = Path(__file__).resolve().parents[3] / 'dataset'


def test_citations_have_explicit_identity_or_unattributed_classification():
    total,reached,negative,misses=analyze(DATASET)
    assert total==reached+len(misses)
    assert negative==sum(m['class']=='negative_scope_unattributed' for m in misses)
    assert all(m['source']!='missing manifest' for m in misses)
    assert all(m['class'] in ('negative_scope_unattributed','unattributed') for m in misses)
    assert all(not m['exists_in_cited_source'] for m in misses if m['class']=='negative_scope_unattributed')


def test_forensic_report_is_deterministic():
    assert report(DATASET)==report(DATASET)
