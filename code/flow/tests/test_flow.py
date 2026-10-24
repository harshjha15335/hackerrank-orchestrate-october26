import csv
import hashlib
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flow.dependencies import build, index_activity, precedence
from flow.engine import (ACTIVE, BLOCKED, CONFLICTING, DISABLED, ENABLED, UNKNOWN, FlowContext,
                         assess_case)
from flow.evidence import read
from flow.main import run_all
from identity.graph import IdentityValue, Resolution
from ingest.evidence import Observation, parse_lines

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / 'dataset'
CACHE = Path('/tmp/m4-ingest-cache')
SUBJECT = 'user_9001'
EMAIL = 'subject.person@example.com'
OTHER = 'someone.else@example.org'
FLOW_ID, BACKUP_ID = 'data_flow_90001', 'backup_90001'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))


@pytest.fixture(scope='module')
def sample_run():
    return run_all(DATASET, sample=True, cache=CACHE)


@pytest.fixture(scope='module')
def full_run():
    return run_all(DATASET, sample=False, cache=CACHE)


def resolution(cutoff, history_email=EMAIL):
    history = (IdentityValue('email', history_email, history_email, 'snapshot'),)
    return Resolution('synthetic_case', cutoff, SUBJECT, (SUBJECT,), 'resolved', {'email': history_email}, history)


def sql_row(table, resource, flag, value, captured, *, owner=EMAIL, evidence='ev_sql'):
    system = {'connector_subscriptions': 'integration_service', 'backup_restore_entries': 'backup_service'}[table]
    raw = {'resource_id': resource, 'customer_reference': None, 'customer_email': owner, flag: value,
           'updated_at': captured}
    return Observation(evidence, 'evidence/databases/x.sql', f'{table}[1]', captured, system, resource, table,
                       None, (), raw, 'sql', table, captured, None, 'synthetic')


def json_entry(system, resource, fields, captured, observed=None, *, evidence='ev_json', locator='$.e[0]'):
    raw = dict(fields, resource_id=resource)
    if observed: raw['observed_at'] = observed
    return Observation(evidence, 'evidence/records/x.json', locator, captured, system, resource, None, None, (),
                       raw, 'json', None, observed, None, 'synthetic')


def log_lines(tmp_path, text, captured, evidence='ev_log'):
    path = tmp_path / f'{evidence}.log'
    path.write_text(text)
    return parse_lines(path, {'file_id': evidence, 'file_path': str(path), 'captured_at': captured}, 'log')


def activity(activity_id, when, event, source, target, resource, details, result='SUCCESS'):
    raw = {'activity_id': activity_id, 'event_time': when, 'event_type': event, 'source_system': source,
           'target_system': target, 'resource_id': resource, 'reported_result': result, 'details': details}
    return Observation(activity_id, 'system_activity.csv', 'row:2', when, None, resource, None, None, (), raw,
                       'activity', None, None, when, None)


def run(observations, cutoff, **kw):
    return {a.resource_id: a for a in assess_case(FlowContext(observations), resolution(cutoff, **kw))}


def ops(a):
    return [(o['phase'], o['operation'], o['state'], o['evidence_id']) for o in a.obligations]


# --- M6-1: ACTIVE -> DISABLED -> ACTIVE at three cut-offs ---------------------

TIMELINE = [sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-03-01T00:00:00Z', evidence='ev_t1'),
            sql_row('connector_subscriptions', FLOW_ID, 'enabled', 0, '2026-05-01T00:00:00Z', evidence='ev_t2'),
            sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-07-01T00:00:00Z', evidence='ev_t3')]


@pytest.mark.parametrize('cutoff,status,evidence', [
    ('2026-04-01T00:00:00Z', ACTIVE, 'ev_t1'),
    ('2026-06-01T00:00:00Z', DISABLED, 'ev_t2'),
    ('2026-08-01T00:00:00Z', ACTIVE, 'ev_t3')])
def test_m6_1_timeline_at_three_cutoffs(cutoff, status, evidence):
    a = run(TIMELINE, cutoff)[FLOW_ID]
    assert a.status == status and a.supported and a.deciding['evidence_id'] == evidence
    if status == ACTIVE:
        assert ops(a) == [('FINDING', 'REPORT_ACTIVE_DATA_FLOW', 'ACTIVE', evidence),
                          ('REMEDIATION', 'DISABLE_DATA_FLOW', 'DISABLED', ''),
                          ('VERIFICATION', 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED', '')]
        assert [o['basis'] for o in a.obligations] == ['observed', 'proposed', 'proposed']
    else:
        assert ops(a) == [('VERIFICATION', 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED', evidence)]


def test_m6_1_cutoff_before_any_evidence_has_no_assessment():
    assert run(TIMELINE, '2026-02-01T00:00:00Z') == {}


def test_m6_1_cutoff_boundary_is_inclusive():
    assert run(TIMELINE, '2026-05-01T00:00:00Z')[FLOW_ID].status == DISABLED
    assert run(TIMELINE, '2026-04-30T23:59:59Z')[FLOW_ID].status == ACTIVE


# --- M6-2: restore enabled -> risk; blocked -> verification only ------------

def backup(value, captured='2026-05-01T00:00:00Z', **kw):
    return sql_row('backup_restore_entries', BACKUP_ID, 'restore_allowed', value, captured, **kw)


def test_m6_2_restore_enabled_is_a_risk():
    a = run([backup(1)], '2026-06-01T00:00:00Z')[BACKUP_ID]
    assert a.status == ENABLED and ops(a) == [('FINDING', 'REPORT_RESTORE_RISK', 'ACTIVE', 'ev_sql'),
                                              ('REMEDIATION', 'BLOCK_RESTORE', 'BLOCKED', ''),
                                              ('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED', '')]


def test_m6_2_restore_blocked_is_verification_only():
    a = run([backup(0)], '2026-06-01T00:00:00Z')[BACKUP_ID]
    assert a.status == BLOCKED and ops(a) == [('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED', 'ev_sql')]


@pytest.mark.parametrize('fields', [{'archive_present': 'true'}, {'restore_allowed': 'maybe'}, {}],
                         ids=['archive_present_only', 'non_boolean', 'missing_flag'])
def test_m6_2_unknown_restore_never_implies_safe(fields):
    entry = json_entry('backup_service', BACKUP_ID, dict(fields, customer_email=EMAIL), '2026-05-01T00:00:00Z')
    a = run([entry], '2026-06-01T00:00:00Z')[BACKUP_ID]
    assert a.status == UNKNOWN and not a.supported and a.obligations == ()


def test_m6_2_found_backup_inventory_is_not_restore_access(tmp_path):
    lines = log_lines(tmp_path, f'- 2026-05-01T00:00:00Z | backup_service | {BACKUP_ID} | BACKUP_ARCHIVE | FOUND | {EMAIL}\n',
                      '2026-05-01T00:00:00Z')
    lines = [l.__class__(**{**l.__dict__, 'source_type': 'txt'}) for l in lines]
    a = run(lines, '2026-06-01T00:00:00Z')[BACKUP_ID]
    assert a.status == UNKNOWN and a.obligations == ()


# --- ownership and attribution ----------------------------------------------

def test_unrelated_customer_process_is_ignored():
    assert run([sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-05-01T00:00:00Z', owner=OTHER)],
               '2026-06-01T00:00:00Z') == {}


def test_active_connector_without_subject_link_is_not_attributed(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=WARN service=integration_service trace_id=tr-1 resource_id={FLOW_ID} '
            'event=connector_heartbeat enabled=true scheduler_registered=true\n')
    assert run(log_lines(tmp_path, text, '2026-05-01T00:00:00Z'), '2026-06-01T00:00:00Z') == {}


def test_trace_join_attributes_identifier_free_heartbeat(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=DEBUG service=integration_service trace_id=tr-1 '
            f'event=connector_config_read_started subject_key="{EMAIL}"\n'
            f'2026-05-01T00:00:01Z level=WARN service=integration_service trace_id=tr-1 resource_id={FLOW_ID} '
            'event=connector_heartbeat enabled=true scheduler_registered=true\n')
    a = run(log_lines(tmp_path, text, '2026-05-01T00:00:05Z'), '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == ACTIVE and a.attribution == 'trace' and a.deciding['evidence_class'] == 'telemetry'


def test_unsafe_trace_with_two_people_is_not_attribution(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=DEBUG service=integration_service trace_id=tr-1 '
            f'event=connector_config_read_started subject_key="{EMAIL}"\n'
            f'2026-05-01T00:00:00Z level=DEBUG service=integration_service trace_id=tr-1 '
            f'event=connector_config_read_started subject_key="{OTHER}"\n'
            f'2026-05-01T00:00:01Z level=WARN service=integration_service trace_id=tr-1 resource_id={FLOW_ID} '
            'event=connector_heartbeat enabled=true scheduler_registered=true\n')
    assert run(log_lines(tmp_path, text, '2026-05-01T00:00:05Z'), '2026-06-01T00:00:00Z') == {}


def test_same_trace_id_in_another_file_is_not_a_join(tmp_path):
    anchor = log_lines(tmp_path, f'2026-05-01T00:00:00Z level=DEBUG service=integration_service trace_id=tr-1 '
                                 f'event=connector_config_read_started subject_key="{EMAIL}"\n',
                       '2026-05-01T00:00:05Z', evidence='ev_a')
    beat = log_lines(tmp_path, f'2026-05-01T00:00:01Z level=WARN service=integration_service trace_id=tr-1 '
                               f'resource_id={FLOW_ID} event=connector_heartbeat enabled=true\n',
                     '2026-05-01T00:00:05Z', evidence='ev_b')
    assert run(anchor + beat, '2026-06-01T00:00:00Z') == {}


def test_reused_resource_id_with_another_owner_is_conflicting():
    mine = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 0, '2026-05-01T00:00:00Z')
    theirs = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-05-02T00:00:00Z', owner=OTHER,
                     evidence='ev_other')
    a = run([mine, theirs], '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == CONFLICTING and not a.supported and a.obligations == ()
    assert a.ownership_conflicts == ('ev_other:connector_subscriptions[1]',)


def test_decoy_backup_for_another_person_is_ignored():
    assert run([backup(1, owner=OTHER)], '2026-06-01T00:00:00Z') == {}


def test_identifier_outside_cutoff_identity_view_is_not_the_subject():
    # The record names an email that is not in the subject's identity view at the cutoff.
    assert run([backup(1)], '2026-06-01T00:00:00Z', history_email='earlier.address@example.com') == {}


# --- temporal safety --------------------------------------------------------

def test_post_cutoff_enablement_is_ignored():
    rows = [sql_row('connector_subscriptions', FLOW_ID, 'enabled', 0, '2026-05-01T00:00:00Z', evidence='ev_a'),
            sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-06-02T00:00:00Z', evidence='ev_b')]
    a = run(rows, '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == DISABLED and a.deciding['evidence_id'] == 'ev_a'


def test_entry_observed_after_capture_or_cutoff_is_inadmissible():
    late = json_entry('integration_service', FLOW_ID, {'enabled': True, 'customer_email': EMAIL},
                      '2026-05-01T00:00:00Z', observed='2026-05-03T00:00:00Z')
    assert run([late], '2026-06-01T00:00:00Z') == {}


def test_quarantined_observation_is_inadmissible():
    row = backup(1)
    ctx = FlowContext([row], anomalies={(row.evidence_id, row.locator)})
    assert assess_case(ctx, resolution('2026-06-01T00:00:00Z')) == []


def test_worker_success_claims_never_set_state():
    claims = [activity('act_1', '2026-05-01T00:00:00Z', 'CHECK_DATA_FLOW', 'deletion_worker', 'integration_service',
                       FLOW_ID, f'Connector status check confirmed that data flow {FLOW_ID} remains enabled.'),
              activity('act_2', '2026-05-02T00:00:00Z', 'DISABLE_DATA_FLOW', 'deletion_worker',
                       'integration_service', FLOW_ID, f'Policy action completed for {FLOW_ID}.')]
    # Claims alone carry no subject link and no state.
    assert run(claims, '2026-06-01T00:00:00Z') == {}
    beat = json_entry('integration_service', FLOW_ID, {'customer_email': EMAIL}, '2026-04-01T00:00:00Z')
    a = run(claims + [beat], '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == UNKNOWN and len(a.claims) == 2


def test_later_disable_claim_does_not_clear_an_observed_active_flow():
    row = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-05-01T00:00:00Z')
    claim = activity('act_9', '2026-05-10T00:00:00Z', 'DISABLE_DATA_FLOW', 'deletion_worker',
                     'integration_service', FLOW_ID, f'Policy action completed for {FLOW_ID}.')
    a = run([row, claim], '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == ACTIVE and a.later_unverified_claims == ('act_9:DISABLED',)


def test_inventory_can_show_risk_but_not_safety(tmp_path):
    def inventory(word):
        lines = log_lines(tmp_path, f'- 2026-05-01T00:00:00Z | integration_service | {FLOW_ID} | DATA_FLOW | {word} | {EMAIL}\n',
                          '2026-05-01T00:00:00Z')
        return [l.__class__(**{**l.__dict__, 'source_type': 'txt'}) for l in lines]
    assert run(inventory('ACTIVE'), '2026-06-01T00:00:00Z')[FLOW_ID].status == ACTIVE
    safe = run(inventory('DISABLED'), '2026-06-01T00:00:00Z')[FLOW_ID]
    assert safe.status == UNKNOWN and safe.obligations == ()


def test_later_unverifiable_safe_listing_after_risk_stays_unresolved(tmp_path):
    row = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-04-01T00:00:00Z')
    lines = log_lines(tmp_path, f'- 2026-05-01T00:00:00Z | integration_service | {FLOW_ID} | DATA_FLOW | DISABLED | {EMAIL}\n',
                      '2026-05-01T00:00:00Z')
    lines = [l.__class__(**{**l.__dict__, 'source_type': 'txt'}) for l in lines]
    assert run([row] + lines, '2026-06-01T00:00:00Z')[FLOW_ID].status == UNKNOWN


# --- inconsistent and incomplete readings -----------------------------------

def test_readback_contradicting_its_row_count_is_unknown(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=INFO service=integration_service trace_id=rb-1 '
            f'event=connector_config_read_completed resource_id={FLOW_ID} enabled=true rows=0 customer_email={EMAIL}\n')
    a = run(log_lines(tmp_path, text, '2026-05-01T00:00:05Z'), '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == UNKNOWN and a.obligations == ()


def test_disagreeing_readings_at_same_time_are_conflicting():
    on = json_entry('integration_service', FLOW_ID, {'enabled': True, 'customer_email': EMAIL},
                    '2026-05-02T00:00:00Z', '2026-05-01T00:00:00Z', evidence='ev_on')
    off = json_entry('integration_service', FLOW_ID, {'enabled': False, 'customer_email': EMAIL},
                     '2026-05-02T00:00:00Z', '2026-05-01T00:00:00Z', evidence='ev_off')
    a = run([on, off], '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == CONFLICTING and a.obligations == ()


def test_missing_or_misplaced_process_identifiers_are_not_processes(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=WARN service=integration_service trace_id=tr-1 '
            f'event=connector_heartbeat enabled=true correlation_key="{EMAIL}"\n'
            f'2026-05-01T00:00:01Z level=WARN service=search_service trace_id=tr-2 resource_id={FLOW_ID} '
            f'event=connector_heartbeat enabled=true correlation_key="{EMAIL}"\n')
    lines = log_lines(tmp_path, text, '2026-05-01T00:00:05Z')
    assert [read(l) for l in lines] == [None, None]
    assert run(lines, '2026-06-01T00:00:00Z') == {}


def test_telemetry_without_owning_service_is_not_state(tmp_path):
    text = (f'2026-05-01T00:00:00Z level=WARN service=queue_consumer resource_id={BACKUP_ID} system=backup_service '
            f'event=restore_candidate_evaluated eligible=true deletion_block=false correlation_key="{EMAIL}"\n')
    a = run(log_lines(tmp_path, text, '2026-05-01T00:00:05Z'), '2026-06-01T00:00:00Z')
    assert all(x.status == UNKNOWN for x in a.values())


@pytest.mark.parametrize('line,status', [
    ('event=restore_authorization_completed decision="deny"', BLOCKED),
    ('event=restore_candidate_evaluated eligible=true deletion_block=false', ENABLED),
    ('event=restore_candidate_evaluated eligible=true deletion_block=true', BLOCKED),
    ('event=restore_candidate_evaluated eligible=true', UNKNOWN)])
def test_restore_telemetry_vocabulary(tmp_path, line, status):
    text = (f'2026-05-01T00:00:00Z level=INFO service=backup_service trace_id=tr-1 resource_id={BACKUP_ID} '
            f'{line} correlation_key="{EMAIL}"\n')
    assert run(log_lines(tmp_path, text, '2026-05-01T00:00:05Z'), '2026-06-01T00:00:00Z')[BACKUP_ID].status == status


# --- dependencies -----------------------------------------------------------

def test_cross_system_dependency_chain_and_precedence():
    flow = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-05-01T00:00:00Z')
    sync = activity('act_s', '2026-05-02T00:00:00Z', 'SYNC_RECORD', 'integration_service', 'search_service',
                    FLOW_ID, 'Active connector repopulated downstream resource search_90001.')
    index = activity('act_i', '2026-05-03T00:00:00Z', 'INDEX_RECORD', 'account_service', 'search_service',
                     'search_90001', 'Customer search-index refresh processed search_90001.')
    other = activity('act_o', '2026-05-02T00:00:00Z', 'SYNC_RECORD', 'integration_service', 'search_service',
                     'data_flow_90002', 'Active connector repopulated downstream resource search_90001.')
    fctx = FlowContext([flow, sync, index, other])
    res = resolution('2026-06-01T00:00:00Z')
    assessments = assess_case(fctx, res)
    resources = [{'system_id': 'search_service', 'resource_id': 'search_90001',
                  'obligations': [('REMEDIATION', 'DELETE_RECORD', 'ABSENT')]},
                 {'system_id': 'account_service', 'resource_id': 'account_90001',
                  'obligations': [('REMEDIATION', 'DELETE_RECORD', 'ABSENT')]}]
    edges = build(fctx, index_activity(fctx.activity), res, assessments, resources, [])
    kinds = {(e['kind'], e['upstream']['resource_id'], e['downstream']['resource_id'], e['evidence_id']) for e in edges}
    # The unassessed connector naming the same downstream record adds no edge.
    assert kinds == {('recreated_by_sync', FLOW_ID, 'search_90001', 'act_s'),
                     ('derived_from_source_system', None, 'search_90001', 'act_i')}
    rules = precedence(assessments, resources, edges)
    firsts = [r for r in rules if r['strength'] == 'contract_rule']
    assert {(r['before']['operation'], r['after']['resource_id']) for r in firsts} == {
        ('DISABLE_DATA_FLOW', 'search_90001'), ('DISABLE_DATA_FLOW', 'account_90001')}
    system = [r for r in rules if r['strength'] == 'system_level']
    assert [(r['before']['resource_id'], r['after']['resource_id']) for r in system] == [('search_90001', 'account_90001')]


def test_dependency_after_cutoff_is_ignored():
    flow = sql_row('connector_subscriptions', FLOW_ID, 'enabled', 1, '2026-05-01T00:00:00Z')
    sync = activity('act_s', '2026-07-02T00:00:00Z', 'SYNC_RECORD', 'integration_service', 'search_service',
                    FLOW_ID, 'Active connector repopulated downstream resource search_90001.')
    fctx = FlowContext([flow, sync])
    res = resolution('2026-06-01T00:00:00Z')
    assert build(fctx, index_activity(fctx.activity), res, assess_case(fctx, res), [], []) == []


# --- participant data -------------------------------------------------------

def test_no_delete_on_backups_and_m5_retention_kept(full_run, sample_run):
    for run_ in (full_run, sample_run):
        assert run_['delete_steps_on_backups'] == 0
        for case in run_['cases']:
            for r in case['restores']:
                assert all(o['operation'] != 'DELETE_RECORD' for o in r['obligations'])
                if 'RETAIN' in r['retention']['m5_required_actions']:
                    assert r['retention']['delete_forbidden']


def test_unknown_and_conflicting_never_have_obligations(full_run):
    for case in full_run['cases']:
        for a in case['flows'] + case['restores']:
            assert a['supported'] == (a['status'] in (ACTIVE, DISABLED, ENABLED, BLOCKED))
            if not a['supported']: assert not a['obligations']
            if a['status'] in (DISABLED, BLOCKED):
                assert a['deciding']['evidence_class'] in ('snapshot', 'readback', 'field_values', 'telemetry')


def test_every_deciding_reading_is_admissible_and_owned(full_run):
    for case in full_run['cases']:
        for a in case['flows'] + case['restores']:
            if a['deciding']:
                d = a['deciding']
                assert d['attribution'] in ('direct', 'trace')
                assert d['captured_at'] <= case['audit_at'] and d['observed_at'] <= case['audit_at']


def test_m6_does_not_change_m4_or_m5_decisions(sample_run):
    from policy.main import run_all as policy_run
    policy = policy_run(DATASET, sample=True, cache=CACHE)
    canon = lambda value: json.dumps(value, sort_keys=True, default=list)
    assert [canon({k: v for k, v in c.items() if k != 'intent'}) for c in policy['cases']] == [
        canon(c['policy']) for c in sample_run['cases']]


def test_m6_3_dev_recall_on_flow_and_restore_steps():
    from evaluation.m6_metrics import evaluate
    report = evaluate(DATASET, CACHE)
    dev = report['process_steps']['dev']
    assert dev['recall'] == 1.0, dev['missed']
    assert dev['precision'] == 1.0, dev['extra']


def test_flow_run_is_deterministic(sample_run):
    again = run_all(DATASET, sample=True, cache=CACHE)
    digest = lambda r: hashlib.sha256(json.dumps(r, sort_keys=True, default=list).encode()).hexdigest()
    assert digest(again) == digest(sample_run)


def test_cli_is_deterministic():
    cmd = [sys.executable, str(ROOT / 'code/flow/main.py'), '--sample', '--summary', '--cache', str(CACHE)]
    first, second = (subprocess.run(cmd, capture_output=True, text=True, check=True).stdout for _ in range(2))
    assert first == second and json.loads(first)['case_count'] == 32


def test_no_sample_answer_identifiers_in_flow_source():
    gold = list(csv.DictReader((DATASET / 'sample_output.csv').open(encoding='utf-8')))
    ids = {r['case_id'] for r in gold}
    for r in gold:
        for step in json.loads(r['steps_json']):
            ids.update(v for v in (step['resource_id'], step['evidence_id']) if v)
    for path in sorted((ROOT / 'code/flow').rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        found = {i for i in ids if re.search(rf'\b{re.escape(i)}\b', text)}
        assert not found, (path, found)


# --- trace anchors must be admissible at the cutoff (M6 safety correction) ---

def heartbeat_trace(tmp_path, anchors, captured='2026-05-01T00:10:00Z', evidence='ev_log'):
    """An identifier-free heartbeat at 00:00:01 plus anchor lines (time, email) in trace tr-1."""
    text = (f'2026-05-01T00:00:01Z level=WARN service=integration_service trace_id=tr-1 resource_id={FLOW_ID} '
            'event=connector_heartbeat enabled=true scheduler_registered=true\n')
    for when, email in anchors:
        text += (f'{when} level=DEBUG service=integration_service trace_id=tr-1 '
                 f'event=connector_config_read_started subject_key="{email}"\n')
    return log_lines(tmp_path, text, captured, evidence=evidence)


def test_post_cutoff_trace_anchor_cannot_attribute_earlier_heartbeat(tmp_path):
    # Heartbeat 05-01, file captured 05-04, anchor stamped 05-06 (after the 05-05 cutoff).
    lines = heartbeat_trace(tmp_path, [('2026-05-06T00:00:00Z', EMAIL)], captured='2026-05-04T00:00:00Z')
    assert run(lines, '2026-05-05T00:00:00Z') == {}
    control = heartbeat_trace(tmp_path, [('2026-05-03T00:00:00Z', EMAIL)], captured='2026-05-04T00:00:00Z')
    assert run(control, '2026-05-05T00:00:00Z')[FLOW_ID].attribution == 'trace'


def test_trace_anchor_stamped_after_its_capture_is_not_evidence(tmp_path):
    # Cutoff long after capture: only the anchor's own time exceeds the manifest capture.
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:20:00Z', EMAIL)], captured='2026-05-01T00:10:00Z')
    assert run(lines, '2026-06-01T00:00:00Z') == {}


def test_quarantined_trace_anchor_cannot_attribute(tmp_path):
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', EMAIL)])
    anchor = next(l for l in lines if 'subject_key' in l.raw_fields)
    ctx = FlowContext(lines, anomalies={(anchor.evidence_id, anchor.locator)})
    assert assess_case(ctx, resolution('2026-06-01T00:00:00Z')) == []


def test_inadmissible_foreign_anchor_keeps_valid_trace_attribution(tmp_path):
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', EMAIL), ('2026-05-01T00:20:00Z', OTHER)])
    a = run(lines, '2026-06-01T00:00:00Z')[FLOW_ID]
    assert a.status == ACTIVE and a.attribution == 'trace'


def test_admissible_subject_and_foreign_anchors_are_ambiguous(tmp_path):
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', EMAIL), ('2026-05-01T00:00:02Z', OTHER)])
    assert run(lines, '2026-06-01T00:00:00Z') == {}


def test_trace_anchor_in_another_file_never_joins(tmp_path):
    beat = heartbeat_trace(tmp_path, [], evidence='ev_beat')
    anchor = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', EMAIL)], evidence='ev_anchor')
    anchor = [l for l in anchor if 'subject_key' in l.raw_fields]
    assert run(beat + anchor, '2026-06-01T00:00:00Z') == {}


def identity_graph(tmp_path):
    from identity.graph import IdentityGraph
    (tmp_path / 'user_identities.csv').write_text(
        'user_id,name,email,phone,email_hash,updated_at\n'
        f'{SUBJECT},Synthetic Person,new.address@example.com,,,2026-07-01T00:00:00Z\n')
    (tmp_path / 'user_audit_log.csv').write_text(
        'audit_id,user_id,event_time,field_name,old_value,new_value\n'
        f'audit_x,{SUBJECT},2026-05-15T00:00:00Z,email,{EMAIL},new.address@example.com\n')
    return IdentityGraph(tmp_path)


def graph_resolution(graph, cutoff, email):
    return graph.resolve({'case_id': 'synthetic_case', 'email': email, 'audit_at': cutoff})


def test_historical_email_at_cutoff_joins_trace(tmp_path):
    graph = identity_graph(tmp_path)
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', EMAIL)])
    res = graph_resolution(graph, '2026-06-01T00:00:00Z', 'new.address@example.com')
    found = assess_case(FlowContext(lines), res)
    assert [(a.resource_id, a.attribution) for a in found] == [(FLOW_ID, 'trace')]


def test_email_acquired_after_cutoff_does_not_join_trace(tmp_path):
    graph = identity_graph(tmp_path)
    lines = heartbeat_trace(tmp_path, [('2026-05-01T00:00:00Z', 'new.address@example.com')])
    res = graph_resolution(graph, '2026-05-10T00:00:00Z', EMAIL)
    assert res.status == 'resolved' and assess_case(FlowContext(lines), res) == []


def test_participant_trace_attributions_are_unchanged(full_run, sample_run):
    """Every participant trace attribution keeps at least one admissible subject anchor."""
    for run_ in (full_run, sample_run):
        traced = [(c, a) for c in run_['cases'] for a in c['flows'] + c['restores'] if a['attribution'] == 'trace']
        assert traced
        for case, a in traced:
            d = a['deciding']
            assert d['observed_at'] <= case['audit_at'] and d['captured_at'] <= case['audit_at']
    assert sum(a['attribution'] == 'trace' for c in full_run['cases'] for a in c['flows'] + c['restores']) == 10
