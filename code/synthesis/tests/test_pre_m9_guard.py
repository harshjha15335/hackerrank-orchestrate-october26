"""Pre-M9 audit hardening of the citation guard and visual diagnostics.

F-05: a table-scope absence citation is re-proved by the guard: the caller's
table name alone never establishes a complete point-in-time absence.
F-02: VERIFY_RECORD_ANONYMIZED needs M5's corroborated anonymization.
F-06: a screenshot captured after audit_at is reported as excluded evidence.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flow.engine import FlowContext
from identity.graph import IdentityValue, Resolution
from identity.retrieval import EvidenceIndex
from identity.snapshots import SnapshotIndex
from ingest.evidence import Observation
from policy.conditions import subject_from
from policy.engine import Context
from synthesis.citations import CitationGuard
from synthesis.tests.test_synthesis import CUTOFF, DATASET, EMAIL, OTHER, SUBJECT, obs, resolution

SQL_HEADER = ('-- Ghost Data Still Exists: point-in-time database snapshot\n'
              '-- Compare the primary and any replica tables for replication drift.\n')
PRIMARY, FAILOVER = 'customer_profiles_primary', 'customer_profiles_failover_replica'
CAPTURED = '2026-09-01T00:00:00Z'


def sql_row(table, n, resource, email, evidence='ev_sql', captured=CAPTURED):
    return Observation(evidence, 'evidence/databases/snap.sql', f'{table}[{n}]', captured, 'account_service',
                       resource, table, None, (), {'resource_id': resource, 'email': email}, 'sql', table)


@pytest.fixture
def snapshot(tmp_path):
    def build(header=SQL_HEADER, rows=None, captured=CAPTURED, tables=(PRIMARY, FAILOVER)):
        (tmp_path / 'evidence' / 'databases').mkdir(parents=True, exist_ok=True)
        (tmp_path / 'evidence' / 'databases' / 'snap.sql').write_text(header + 'CREATE TABLE x (y);\n')
        rows = rows if rows is not None else [sql_row(PRIMARY, 1, 'account_9', EMAIL, captured=captured),
                                              sql_row(FAILOVER, 1, 'account_8', OTHER, captured=captured)]
        coverage = [{'format': '.sql', 'file_id': 'ev_sql', 'source_path': 'evidence/databases/snap.sql',
                     'tables': {t: 1 for t in tables}}]
        times = {'ev_sql': datetime.fromisoformat(captured.replace('Z', '+00:00'))}
        config = Context([], DATASET / 'deletion_rules.csv').config
        guard = CitationGuard(rows, times, set(), FlowContext(rows), {'ev_sql': set(tables)}, config,
                              SnapshotIndex(rows, coverage), tmp_path)
        return guard
    return build


def absent_step(resource='account_9', system='account_service'):
    return {'step_no': 1, 'phase': 'VERIFICATION', 'system_id': system, 'resource_id': resource,
            'operation': 'VERIFY_RECORD_ABSENT', 'state': 'ABSENT', 'evidence_id': 'ev_sql'}


def check(guard, step=None, table=FAILOVER, scope=None, resource='account_9'):
    step = step or absent_step(resource)
    provenance = {'kind': 'm4', 'evidence_id': 'ev_sql', 'locator': f'{table}:no-row:{resource}',
                  'scope': scope if scope is not None else table}
    res = resolution()
    return guard.check('synthetic_case', step, provenance, res, subject_from(res))


def test_valid_complete_snapshot_absence_is_preserved(snapshot):
    verdict = check(snapshot())
    assert verdict.accepted, verdict.reason


def test_caller_table_name_without_completeness_is_rejected(snapshot):
    verdict = check(snapshot(header='-- export of selected rows\n'))
    assert not verdict.accepted and 'complete point-in-time' in verdict.reason


def test_guard_without_snapshot_index_cannot_prove_absence():
    rows = [sql_row(PRIMARY, 1, 'account_9', EMAIL)]
    times = {'ev_sql': datetime.fromisoformat(CAPTURED.replace('Z', '+00:00'))}
    guard = CitationGuard(rows, times, set(), FlowContext(rows), {'ev_sql': {PRIMARY, FAILOVER}},
                          Context([], DATASET / 'deletion_rules.csv').config)
    assert check(guard).reason == 'table completeness cannot be verified'


def test_absence_needs_independent_subject_attribution(snapshot):
    foreign = [sql_row(PRIMARY, 1, 'account_9', OTHER), sql_row(FAILOVER, 1, 'account_8', OTHER)]
    assert 'independently attributed' in check(snapshot(rows=foreign)).reason
    nothing = [sql_row(FAILOVER, 1, 'account_8', OTHER)]
    assert 'independently attributed' in check(snapshot(rows=nothing)).reason


def test_absence_must_describe_the_steps_physical_copy(snapshot):
    verdict = check(snapshot(), scope='service')
    assert not verdict.accepted and 'does not describe copy' in verdict.reason


def test_absence_of_a_table_the_snapshot_lacks_is_rejected(snapshot):
    verdict = check(snapshot(tables=(PRIMARY,)))
    assert verdict.reason == 'cited snapshot has no such table scope'


def test_absence_in_another_systems_table_is_rejected(snapshot):
    verdict = check(snapshot(), step=absent_step(system='search_service'))
    assert not verdict.accepted and 'does not belong' in verdict.reason


def test_table_that_still_holds_the_row_is_not_absence(snapshot):
    rows = [sql_row(PRIMARY, 1, 'account_9', EMAIL), sql_row(FAILOVER, 1, 'account_9', EMAIL)]
    assert check(snapshot(rows=rows)).reason == 'cited table still contains the resource'


def test_snapshot_after_audit_at_is_rejected(snapshot):
    verdict = check(snapshot(captured='2026-09-11T00:00:00Z'))
    assert verdict.reason == 'evidence captured after audit_at'


def test_anonymized_verification_needs_corroborated_anonymization():
    o = obs('ev_a', '$.r[0]', 'analytics_platform', 'analytics_9',
            {'resource_id': 'analytics_9', 'email': None, 'user_id': None, 'metrics': {'x': 1},
             'customer_reference': SUBJECT})
    times = {'ev_a': datetime.fromisoformat(o.captured_at.replace('Z', '+00:00'))}
    guard = CitationGuard([o], times, set(), FlowContext([o]), {}, Context([], DATASET / 'deletion_rules.csv').config)
    step = {'step_no': 1, 'phase': 'VERIFICATION', 'system_id': 'analytics_platform', 'resource_id': 'analytics_9',
            'operation': 'VERIFY_RECORD_ANONYMIZED', 'state': 'ANONYMIZED', 'evidence_id': 'ev_a'}
    res = resolution()
    provenance = {'kind': 'm4', 'evidence_id': 'ev_a', 'locator': '$.r[0]', 'scope': 'service'}
    verdict = guard.check('c', step, provenance, res, subject_from(res))
    assert verdict.reason == 'irreversible anonymization was not evidenced for the cited record'
    proven = guard.check('c', step, dict(provenance, anonymization_proven=True), res, subject_from(res))
    assert proven.accepted, proven.reason


def image(captured, record_time=None):
    return Observation('ev_img', 'evidence/images/x.png', 'image:row', captured, 'export_service', 'export_9', None,
                       None, ((EMAIL, EMAIL),), {'resource_id': 'export_9', 'owner_email': EMAIL}, 'image',
                       None, record_time, None, 'export_service')


def test_future_captured_screenshot_is_excluded_not_dropped():
    res = resolution()
    index = EvidenceIndex([image('2026-09-11T00:00:00Z')])
    assert index.find(res) == []
    assert [h.observation.locator for h in index.excluded_visual(res)] == ['image:row']


def test_admissible_screenshot_is_found_not_excluded():
    res = resolution()
    index = EvidenceIndex([image('2026-09-09T00:00:00Z')])
    assert [h.observation.locator for h in index.find(res)] == ['image:row']
    assert index.excluded_visual(res) == []


def test_future_non_image_evidence_is_neither_found_nor_reported():
    res = resolution()
    log = Observation('ev_log', 'evidence/logs/x.log', 'line:1', '2026-09-11T00:00:00Z', 'export_service',
                      'export_9', None, None, ((EMAIL, EMAIL),), {'resource_id': 'export_9', 'owner_email': EMAIL},
                      'log')
    index = EvidenceIndex([log])
    assert index.find(res) == [] and index.excluded_visual(res) == []
