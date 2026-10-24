"""Measure public dev citations only in evaluation; do not encode a miss as success."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from evaluation.m2_forensics import (analyze, report, independent_gate,
                                      assert_revised_gate, historical_only_recount)
from identity.retrieval import EvidenceIndex
from ingest.evidence import ingest

DATASET = Path(__file__).resolve().parents[3] / 'dataset'


def test_citations_have_explicit_identity_or_unattributed_classification():
    total,reached,negative,misses=analyze(DATASET)
    assert total==reached+len(misses)
    assert negative==sum(m['class']=='negative_scope_unattributed' for m in misses)
    assert all(m['source']!='missing manifest' for m in misses)
    assert all(m['class'] in ('negative_scope_unattributed','unattributed') for m in misses)
    assert all(not m['exists_in_cited_source'] for m in misses if m['class']=='negative_scope_unattributed')
    metrics=independent_gate(DATASET)
    assert_revised_gate(metrics)
    assert metrics['original_hits']==31 and metrics['total']==38
    assert metrics['negative_scopes']==3 and metrics['unattributed']==4


def test_removing_identifier_postings_fails_independent_gate():
    observations,_,_=ingest(DATASET)
    index=EvidenceIndex(observations)
    assert index.postings
    index.postings.clear()  # deliberate retrieval regression; oracle reads raw source
    metrics=independent_gate(DATASET,index_override=index)
    assert metrics['supported']>0 and metrics['supported_hits']<metrics['supported']
    with pytest.raises(AssertionError, match='source-backed identity citation missing'):
        assert_revised_gate(metrics)


def test_forensic_report_is_deterministic():
    assert report(DATASET)==report(DATASET)


def test_historical_only_recount_uses_source_csvs():
    total,current,historical=historical_only_recount(DATASET)
    assert total==current+historical
    assert (total,current,historical)==(518,418,100)
