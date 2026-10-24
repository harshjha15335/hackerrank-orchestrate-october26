import csv
import hashlib
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from identity.graph import IdentityValue, Resolution
from ingest.evidence import Observation
from policy.categories import classify, load_map
from policy.conditions import FALSE, TRUE, UNKNOWN, load_config
from policy.engine import (COMPLIANT, DEFERRED, UNRESOLVED, VIOLATION, Context, decide_copy,
                           rollup)
from policy.conditions import subject_from
from policy.main import run_all
from policy.rules import PolicyError, load_rules

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / 'dataset'
RULES = DATASET / 'deletion_rules.csv'
CACHE = Path('/tmp/m4-ingest-cache')
T = '2026-09-10T12:00:00Z'
SUBJECT_EMAIL = 'subject.person@example.com'
OTHER_EMAIL = 'someone.else@example.org'
SUBJECT_HASH = 'a' * 64
SUBJECT = 'user_9001'


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


def resolution(cutoff=T):
    history = (IdentityValue('email', SUBJECT_EMAIL, SUBJECT_EMAIL, 'snapshot'),
               IdentityValue('email_hash', SUBJECT_HASH, SUBJECT_HASH, 'snapshot'),
               IdentityValue('phone', '+1 555 010 0200', '15550100200', 'snapshot'))
    return Resolution('synthetic_case', cutoff, SUBJECT, (SUBJECT,), 'resolved',
                      {'email': SUBJECT_EMAIL}, history)


def obs(fields, system, resource, *, category=None, kind='json', evidence='synthetic_evidence',
        locator='$.records[0]', captured=T, record_time=None):
    return Observation(evidence, 'evidence/synthetic.json', locator, captured, system, resource, category,
                       None, (), dict(fields, resource_id=resource), kind, None, record_time, None, 'synthetic')


def decide(fields, system, resource, state, *, category=None, rules=RULES, extra=(), kind='json',
           cutoff=T, bindings=None):
    o = obs(fields, system, resource, category=category, kind=kind)
    ctx = Context([o, *extra], rules if isinstance(rules, Path) else rules, bindings=bindings)
    latest = {'system_id': system, 'resource_id': resource, 'topology': 'service', 'state': state,
              'supported': state != 'UNKNOWN', 'explanation': 'synthetic', 'evidence_id': o.evidence_id,
              'locator': o.locator}
    res = resolution(cutoff)
    return decide_copy(ctx, latest, [latest], res, subject_from(res))


def ops(decision):
    return [op for _, op, _ in decision.obligations + decision.restore_obligations]


# Coverage table used by the generated condition-coverage report. Each entry is
# backed by one parametrized case below (checked by test_coverage_table_is_exercised).
CASES = [
    # category, outcome, fields, system, resource, state, label, compliance, operations
    ('USER_PROFILE', 'ALWAYS', {'email': SUBJECT_EMAIL}, 'account_service', 'account_9', 'PRESENT', None,
     VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('USER_PROFILE', 'ALWAYS', {}, 'account_service', 'account_9', 'ABSENT', None, COMPLIANT, ['VERIFY_RECORD_ABSENT']),
    ('SECONDARY_IDENTIFIER', 'ALWAYS', {'email': SUBJECT_EMAIL}, 'identity_service', 'alias_9', 'PRESENT',
     'SECONDARY_IDENTIFIER', VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('SEARCH_INDEX_ENTRY', 'ALWAYS', {'display_name': 'S P'}, 'search_service', 'search_9', 'PRESENT', None,
     VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('CACHE_ENTRY', 'ALWAYS', {'email': SUBJECT_EMAIL}, 'cache_service', 'cache_9', 'ABSENT', None,
     COMPLIANT, ['VERIFY_RECORD_ABSENT']),
    ('USER_EXPORT', 'ALWAYS', {'owner_email': SUBJECT_EMAIL}, 'export_service', 'export_9', 'PRESENT', None,
     VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('MARKETING_PROFILE', 'ALWAYS', {'email_opt_in': 'true'}, 'analytics_platform', 'analytics_9', 'PRESENT',
     None, VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('SUPPORT_MESSAGE', TRUE, {'ticket_id': 'CS-1', 'message_text': f'Send the order update to {SUBJECT_EMAIL}.',
                               'subject_reference': SUBJECT}, 'support_platform', 'support_9', 'PRESENT', None,
     VIOLATION, ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED']),
    ('SUPPORT_MESSAGE', TRUE, {'ticket_id': 'CS-1', 'message_text': '[REDACTED]', 'subject_reference': SUBJECT},
     'support_platform', 'support_9', 'REDACTED', None, COMPLIANT, ['VERIFY_RECORD_REDACTED']),
    ('SUPPORT_MESSAGE', FALSE, {'message_excerpt': 'Please close my profile.', 'requester_email': SUBJECT_EMAIL},
     'support_platform', 'support_9', 'PRESENT', None, VIOLATION,
     ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('SUPPORT_MESSAGE', UNKNOWN, {'requester_email': SUBJECT_EMAIL}, 'support_platform', 'support_9', 'PRESENT',
     'SUPPORT_MESSAGE', UNRESOLVED, []),
    ('SUPPORT_ATTACHMENT', TRUE, {'file_name': 'receipt.pdf', 'uploaded_by': SUBJECT_EMAIL}, 'support_platform',
     'support_9', 'PRESENT', None, VIOLATION, ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('SUPPORT_ATTACHMENT', FALSE, {'file_name': 'receipt.pdf', 'uploaded_by': OTHER_EMAIL}, 'support_platform',
     'support_9', 'PRESENT', None, UNRESOLVED, []),
    ('SUPPORT_ATTACHMENT', UNKNOWN, {'file_name': 'receipt.pdf'}, 'support_platform', 'support_9', 'PRESENT',
     None, UNRESOLVED, []),
    ('ANALYTICS_PROFILE', TRUE, {'email': SUBJECT_EMAIL, 'audience_cohort': 'x'}, 'analytics_platform',
     'analytics_9', 'PRESENT', None, VIOLATION, ['REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED']),
    ('ANALYTICS_PROFILE', FALSE, {'email': None, 'phone': None, 'customer_reference': None, 'audience_cohort': 'x'},
     'analytics_platform', 'analytics_9', 'PRESENT', None, COMPLIANT, ['VERIFY_RECORD_ANONYMIZED']),
    ('ANALYTICS_PROFILE', UNKNOWN, {'audience_cohort': 'x'}, 'analytics_platform', 'analytics_9', 'PRESENT',
     None, UNRESOLVED, []),
    ('PRODUCT_TELEMETRY', TRUE, {'user_id': SUBJECT, 'metrics': {'clicks': 3}}, 'telemetry_service', 'telemetry_9',
     'PRESENT', None, VIOLATION, ['REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED']),
    ('PRODUCT_TELEMETRY', FALSE, {'user_id': None, 'email': None, 'metrics': {'clicks': 3}}, 'telemetry_service',
     'telemetry_9', 'PRESENT', None, COMPLIANT, ['VERIFY_RECORD_ANONYMIZED']),
    ('PRODUCT_TELEMETRY', UNKNOWN, {'device': 'x'}, 'telemetry_service', 'telemetry_9', 'PRESENT', None,
     UNRESOLVED, []),
    ('EMAIL_DELIVERY_LOG', TRUE, {'recipient': SUBJECT_EMAIL, 'status': 'sent'}, 'notification_service',
     'email_delivery_9', 'PRESENT', None, VIOLATION, ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED']),
    ('EMAIL_DELIVERY_LOG', FALSE, {'recipient': None, 'status': 'sent'}, 'notification_service', 'email_delivery_9',
     'PRESENT', None, COMPLIANT, ['VERIFY_RECORD_REDACTED']),
    ('EMAIL_DELIVERY_LOG', UNKNOWN, {}, 'notification_service', 'email_delivery_9', 'PRESENT', None, UNRESOLVED, []),
    ('SECURITY_AUDIT_LOG', TRUE, {'subject_reference': SUBJECT, 'retention_until': '2031-01-01T00:00:00Z'},
     'security_service', 'audit_record_9', 'PRESENT', None, COMPLIANT, ['VERIFY_RECORD_PRESENT']),
    ('SECURITY_AUDIT_LOG', FALSE, {'subject_reference': SUBJECT, 'retention_until': '2026-01-01T00:00:00Z'},
     'security_service', 'audit_record_9', 'PRESENT', None, VIOLATION,
     ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('SECURITY_AUDIT_LOG', UNKNOWN, {'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
     None, UNRESOLVED, []),
    ('LEGAL_HOLD_RECORD', TRUE, {'retained_until': '2033-01-01T00:00:00Z', 'retention_reason': 'dispute'},
     'legal_service', 'legal_hold_9', 'PRESENT', None, COMPLIANT, ['VERIFY_RECORD_PRESENT']),
    ('LEGAL_HOLD_RECORD', FALSE, {'retained_until': '2026-01-01T00:00:00Z', 'retention_reason': 'dispute'},
     'legal_service', 'legal_hold_9', 'PRESENT', None, VIOLATION,
     ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT']),
    ('LEGAL_HOLD_RECORD', UNKNOWN, {'retained_until': '2033-01-01T00:00:00Z'}, 'legal_service', 'legal_hold_9',
     'PRESENT', None, UNRESOLVED, []),
    ('BACKUP_ARCHIVE', TRUE, {'restore_allowed': True}, 'backup_service', 'backup_9', 'RESTORE_ENABLED', None,
     COMPLIANT, ['REPORT_RESTORE_RISK', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED']),
    ('BACKUP_ARCHIVE', TRUE, {'restore_allowed': False}, 'backup_service', 'backup_9', 'RESTORE_BLOCKED', None,
     COMPLIANT, ['VERIFY_RESTORE_BLOCKED']),
    ('BACKUP_ARCHIVE', UNKNOWN, {'archive_key': 'k'}, 'backup_service', 'backup_9', 'UNKNOWN', None, UNRESOLVED, []),
    ('ACCOUNT_TOMBSTONE', TRUE, {'subject_reference': SUBJECT, 'name': 'S P', 'email': SUBJECT_EMAIL, 'phone': None,
                                 'email_hash': SUBJECT_HASH, 'account_status': 'DELETED'}, 'identity_service',
     'tombstone_9', 'PRESENT', None, VIOLATION, ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED']),
    ('ACCOUNT_TOMBSTONE', TRUE, {'subject_reference': SUBJECT, 'name': None, 'email': None, 'phone': None,
                                 'email_hash': None, 'account_status': 'DELETED'}, 'identity_service',
     'tombstone_9', 'REDACTED', None, COMPLIANT, ['VERIFY_RECORD_REDACTED']),
    ('ACCOUNT_TOMBSTONE', FALSE, {'subject_reference': SUBJECT, 'account_status': 'ACTIVE'}, 'identity_service',
     'tombstone_9', 'PRESENT', None, UNRESOLVED, []),
    ('ACCOUNT_TOMBSTONE', UNKNOWN, {'subject_reference': SUBJECT}, 'identity_service', 'tombstone_9', 'PRESENT',
     None, UNRESOLVED, []),
]
COVERAGE = sorted({(c[0], c[1]) for c in CASES})


@pytest.mark.parametrize('case', CASES, ids=[f'{c[0]}-{c[1]}-{c[5]}' for c in CASES])
def test_m5_2_rule_condition_fixture(case):
    category, outcome, fields, system, resource, state, label, compliance, operations = case
    d = decide(fields, system, resource, state, category=label)
    assert d.category == category and d.category_status == 'MAPPED'
    assert d.condition_outcome == (TRUE if outcome == 'ALWAYS' else outcome)
    assert d.compliance == compliance, d.reason
    assert ops(d) == operations


def test_coverage_table_is_exercised():
    rules = load_rules(RULES)
    covered = {category for category, _ in COVERAGE}
    assert covered == set(rules.categories)
    for rule in rules.rules:
        outcomes = {o for c, o in COVERAGE if c == rule.data_category}
        if rule.unconditional:
            assert outcomes == {'ALWAYS'}
        elif rule.data_category == 'BACKUP_ARCHIVE':
            # No observation can show that restore access is impossible to block.
            assert outcomes == {TRUE, UNKNOWN}
        else:
            assert outcomes == {TRUE, FALSE, UNKNOWN}, rule.data_category


# --- M5-1: rules are data -----------------------------------------------------

def test_m5_1_rules_load_from_csv():
    table = load_rules(RULES)
    with RULES.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(table.rules) == len(rows) == 15
    assert [(r.rule_id, r.data_category, r.condition, r.required_action) for r in table.rules] == \
        [(r['rule_id'], r['data_category'], r['condition'], r['required_action']) for r in rows]


def test_m5_1_no_rule_text_in_code():
    sources = '\n'.join(p.read_text() for p in (ROOT / 'code/policy').rglob('*.py') if p.name != 'test_policy.py')
    for rule in load_rules(RULES).rules:
        if not rule.unconditional:
            assert rule.condition not in sources
            assert rule.condition.casefold()[:40] not in sources.casefold()


def rewrite(tmp_path, change):
    rows = list(csv.DictReader(RULES.open(newline='', encoding='utf-8')))
    for row in rows: change(row)
    path = tmp_path / 'deletion_rules.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return path


def test_m5_1_changing_csv_action_changes_decision(tmp_path):
    before = decide({'email': SUBJECT_EMAIL}, 'search_service', 'search_9', 'PRESENT')
    path = rewrite(tmp_path, lambda r: r.update(required_action='RETAIN')
                   if r['data_category'] == 'SEARCH_INDEX_ENTRY' else None)
    after = decide({'email': SUBJECT_EMAIL}, 'search_service', 'search_9', 'PRESENT', rules=path)
    assert (before.effective_action, before.compliance) == ('DELETE', VIOLATION)
    assert (after.effective_action, after.compliance, ops(after)) == ('RETAIN', COMPLIANT, ['VERIFY_RECORD_PRESENT'])


def test_m5_1_changing_csv_changes_full_sample_run(tmp_path, sample_run):
    path = rewrite(tmp_path, lambda r: r.update(required_action='ANONYMIZE')
                   if r['data_category'] == 'USER_PROFILE' else None)
    changed = run_all(DATASET, sample=True, cache=CACHE, rules=path)
    actions = lambda run: [d['effective_action'] for c in run['cases'] for d in c['decisions']
                           if d['category'] == 'USER_PROFILE']
    assert set(actions(sample_run)) == {'DELETE'}
    assert set(actions(changed)) == {'ANONYMIZE'}


def test_m5_1_cli_accepts_alternative_rules(tmp_path):
    path = rewrite(tmp_path, lambda r: r.update(required_action='RETAIN')
                   if r['data_category'] == 'USER_PROFILE' else None)
    out = subprocess.run([sys.executable, str(ROOT / 'code/policy/main.py'), '--sample', '--summary',
                          '--rules', str(path)], capture_output=True, text=True, check=True)
    summary = json.loads(out.stdout)
    assert next(r for r in summary['rules'] if r['data_category'] == 'USER_PROFILE')['required_action'] == 'RETAIN'


def test_m5_1_changed_condition_wording_is_unbound(tmp_path):
    path = rewrite(tmp_path, lambda r: r.update(condition=r['condition'] + ' and the agent consents')
                   if r['data_category'] == 'SUPPORT_MESSAGE' else None)
    d = decide({'ticket_id': 'CS-1', 'message_text': SUBJECT_EMAIL}, 'support_platform', 'support_9', 'PRESENT',
               rules=path)
    assert (d.condition_outcome, d.compliance) == (UNKNOWN, UNRESOLVED)
    assert 'no bound predicate' in d.condition_reason


@pytest.mark.parametrize('mutate,message', [
    (lambda r: r.update(required_action='PURGE') if r['rule_id'].endswith('01') else None, 'unknown action'),
    (lambda r: r.update(data_category='USER_PROFILE') if r['rule_id'].endswith('02') else None, 'duplicate'),
    (lambda r: r.update(condition='') if r['rule_id'].endswith('03') else None, 'empty'),
])
def test_invalid_rule_files_fail_loudly(tmp_path, mutate, message):
    with pytest.raises(PolicyError, match=message):
        load_rules(rewrite(tmp_path, mutate))


# --- M5-3: tombstones from participant snapshot bundles -----------------------

def bundle_tombstones():
    records = []
    for path in sorted((DATASET / 'evidence/records').glob('customer_data_snapshot_bundle_*.json')):
        for snapshot in json.loads(path.read_text())['snapshots']:
            if snapshot['collection'] == 'deleted_customer_references':
                records.extend(snapshot['records'])
    return records


def test_m5_3_tombstone_fixture_from_snapshot_bundle():
    records = bundle_tombstones()
    exposed = [r for r in records if any(r.get(f) for f in ('name', 'email', 'phone', 'email_hash'))]
    clean = [r for r in records if not any(r.get(f) for f in ('name', 'email', 'phone', 'email_hash'))]
    assert exposed and clean
    config = load_config()
    for record in exposed + clean:
        reference = record['subject_reference']
        res = Resolution('synthetic_case', T, reference, (reference,), 'resolved',
                         {'email': record['email']},
                         (IdentityValue('email', record['email'], record['email'].casefold(), 's'),)
                         if record['email'] else ())
        o = obs({k: v for k, v in record.items() if k != 'resource_id'}, 'identity_service', record['resource_id'])
        ctx = Context([o], RULES)
        state = 'PRESENT' if record in exposed else 'REDACTED'
        latest = {'system_id': 'identity_service', 'resource_id': record['resource_id'], 'topology': 'service',
                  'state': state, 'supported': True, 'explanation': 'fixture', 'evidence_id': o.evidence_id,
                  'locator': o.locator}
        d = decide_copy(ctx, latest, [latest], res, subject_from(res))
        assert d.category == 'ACCOUNT_TOMBSTONE' and d.condition_outcome == TRUE
        assert 'subject_reference' not in d.exposed_fields
        if record in exposed:
            assert d.compliance == VIOLATION
            assert set(d.exposed_fields) == {f for f in ('name', 'email', 'phone', 'email_hash') if record[f]}
            assert ops(d) == ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED']
        else:
            assert d.compliance == COMPLIANT and ops(d) == ['VERIFY_RECORD_REDACTED']
    assert config['permitted_fields']['ACCOUNT_TOMBSTONE'] == ['subject_reference']


# --- M5-4: retained records are never deleted ---------------------------------

def test_m5_4_no_delete_on_retain_categories(full_run, sample_run):
    for run in (full_run, sample_run):
        assert run['retain_category_delete_steps'] == 0
        for case in run['cases']:
            for d in case['decisions']:
                if d['required_action'] == 'RETAIN' and d['condition_outcome'] in (TRUE, UNKNOWN):
                    assert d['effective_action'] in ('RETAIN', None)
                    assert not any(op == 'DELETE_RECORD' for _, op, _ in d['obligations'])
                if d['effective_action'] == 'RETAIN' and d['compliance'] == COMPLIANT:
                    verify = [op for _, op, _ in d['obligations'] + d['restore_obligations']]
                    assert verify and set(verify) <= {'VERIFY_RECORD_PRESENT', 'REPORT_RESTORE_RISK',
                                                      'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED'}


# --- engine safety ------------------------------------------------------------

def test_unknown_state_is_never_compliant(full_run):
    decisions = [d for c in full_run['cases'] for d in c['decisions']]
    assert decisions
    assert not any(d['compliance'] == COMPLIANT and not d['state_supported'] for d in decisions)
    assert not any(d['compliance'] == COMPLIANT and d['category_status'] != 'MAPPED' for d in decisions)


def test_unmapped_and_ambiguous_categories_are_unresolved():
    unmapped = decide({'payload': 'x'}, 'unknown_service', 'thing_9', 'PRESENT')
    assert (unmapped.category_status, unmapped.compliance) == ('UNMAPPED', UNRESOLVED)
    ambiguous = decide({'message_text': 'order', 'file_name': 'x.pdf'}, 'support_platform', 'support_9', 'PRESENT')
    assert (ambiguous.category_status, ambiguous.compliance) == ('AMBIGUOUS', UNRESOLVED)


def test_flow_resources_are_deferred_to_m6():
    d = decide({'enabled': True, 'connector_name': 'crm'}, 'integration_service', 'data_flow_9', 'ACTIVE')
    assert (d.category, d.compliance, d.obligations) == ('DATA_FLOW', DEFERRED, ())


def test_condition_attribute_from_other_copy_and_cutoff():
    term = obs({'subject_reference': SUBJECT, 'retention_until': '2030-01-01T00:00:00Z'}, 'security_service',
               'audit_record_9', evidence='synthetic_ledger', locator='$.records[1]')
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT', extra=[term])
    assert (d.condition_outcome, d.compliance) == (TRUE, COMPLIANT)
    later = obs({'subject_reference': SUBJECT, 'retention_until': '2030-01-01T00:00:00Z'}, 'security_service',
                'audit_record_9', evidence='synthetic_ledger', locator='$.records[1]', captured='2026-12-01T00:00:00Z')
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT', extra=[later])
    assert d.condition_outcome == UNKNOWN
    foreign = obs({'subject_reference': 'user_9002', 'retention_until': '2030-01-01T00:00:00Z'}, 'security_service',
                  'audit_record_9', evidence='synthetic_ledger', locator='$.records[1]')
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT', extra=[foreign])
    assert d.condition_outcome == UNKNOWN


def test_retention_boundary_is_inclusive():
    at = decide({'retention_until': T}, 'security_service', 'audit_record_9', 'PRESENT')
    before = decide({'retention_until': '2026-09-10T11:59:59Z'}, 'security_service', 'audit_record_9', 'PRESENT')
    assert (at.condition_outcome, before.condition_outcome) == (TRUE, FALSE)


def test_document_retention_term():
    lines = ['Event reference audit_record_9', 'subject reference user_9001', 'retain until 25 Aug 2027 04 03 UTC']
    docs = [obs({'text': text}, None, None, kind='pdf', evidence='synthetic_pdf', locator=f'line:{n}')
            for n, text in enumerate(lines, 1)]
    docs = [Observation(o.evidence_id, o.source_path, o.locator, o.captured_at, None, None, None, None, (),
                        {'text': o.raw_fields['text']}, 'pdf') for o in docs]
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT', extra=docs)
    assert (d.condition_outcome, d.condition_evidence) == (TRUE, ('synthetic_pdf',))


def test_physical_copy_rollup_reports_worst_copy():
    primary = decide({}, 'account_service', 'account_9', 'ABSENT')
    replica = decide({'email': SUBJECT_EMAIL}, 'account_service', 'account_9', 'PRESENT')
    from dataclasses import replace
    resources = rollup([primary, replace(replica, topology='failover_replica')])
    assert len(resources) == 1 and resources[0]['compliance'] == VIOLATION and resources[0]['copies'] == 2


def test_free_text_identifier_is_exposure_but_stable_reference_is_not():
    d = decide({'ticket_id': 'CS-1', 'subject_reference': SUBJECT,
                'message_text': f'Order update for {SUBJECT_EMAIL}'}, 'support_platform', 'support_9', 'REDACTED')
    assert d.exposed_fields == ('message_text',) and d.compliance == VIOLATION


def test_category_signal_ranks():
    cmap = load_map()
    cats = load_rules(RULES).categories
    contact = obs({'email_opt_in': 'true'}, 'analytics_platform', 'analytics_9')
    assert classify([contact], 'analytics_platform', 'analytics_9', cats, cmap).category == 'MARKETING_PROFILE'
    plain = obs({'audience_cohort': 'x'}, 'analytics_platform', 'analytics_9')
    assert classify([plain], 'analytics_platform', 'analytics_9', cats, cmap).basis == 'resource_prefix'
    labelled = obs({}, 'support_platform', 'support_9', category='SUPPORT_ATTACHMENT')
    assert classify([labelled], 'support_platform', 'support_9', cats, cmap).category == 'SUPPORT_ATTACHMENT'


def test_unknown_report_accounts_for_every_m4_unknown(full_run):
    unresolved = sum(1 for c in full_run['cases'] for d in c['decisions'] if not d['state_supported'])
    rows = full_run['unknown_root_causes']
    assert len(rows) == unresolved
    assert all(r['primary_cause'] in r['causes'] for r in rows)


def test_policy_run_is_deterministic(sample_run):
    again = run_all(DATASET, sample=True, cache=CACHE)
    digest = lambda run: hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()
    assert digest(again) == digest(sample_run)


def test_m5_5_dev_metrics_are_reported():
    sys.path.insert(0, str(ROOT / 'code'))
    from evaluation.m5_metrics import evaluate
    report = evaluate(DATASET, CACHE)
    dev = report['strict']['dev']
    assert set(dev['status_basis']) and len(dev['status_basis']) == 22
    for key in ('status_accuracy', 'step_f1', 'sequence_accuracy'):
        assert 0 <= dev['all_steps'][key] <= 1


# --- cross-customer attribution (M5 review correction) ------------------------

def retention_term(fields, *, evidence='synthetic_ledger', locator='$.records[1]', captured=T):
    return obs(dict(fields, retention_until='2030-01-01T00:00:00Z'), 'security_service', 'audit_record_9',
               evidence=evidence, locator=locator, captured=captured)


@pytest.mark.parametrize('identity', [
    {'customer_email': OTHER_EMAIL},
    {'phone': '+44 20 7946 0999'},
    {'email_hash': 'b' * 64},
    {'subject_reference': 'user_9002'},
    {'subject_reference': SUBJECT, 'customer_email': OTHER_EMAIL},
    {'message_text': f'forwarded from {OTHER_EMAIL}'},
], ids=['email', 'phone', 'email_hash', 'user_ref', 'mixed', 'free_text'])
def test_other_customer_same_resource_id_is_ignored(identity):
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
               extra=[retention_term(identity)])
    assert (d.condition_outcome, d.compliance) == (UNKNOWN, UNRESOLVED)


@pytest.mark.parametrize('identity', [
    {'subject_reference': SUBJECT}, {'customer_email': SUBJECT_EMAIL.upper()},
    {'phone': '+1 (555) 010-0200'}, {'email_hash': SUBJECT_HASH},
], ids=['user_ref', 'email_case', 'phone_format', 'email_hash'])
def test_same_subject_retention_evidence_is_used(identity):
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
               extra=[retention_term(identity)])
    assert (d.condition_outcome, d.compliance) == (TRUE, COMPLIANT)
    assert d.condition_evidence == ('synthetic_ledger:$.records[1]',)


def test_unattributed_record_cannot_supply_retention_date():
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
               extra=[retention_term({})])
    assert d.condition_outcome == UNKNOWN


def test_cross_topology_copies_need_their_own_attribution():
    replica = Observation('synthetic_sql', 'evidence/synthetic.sql', 'security_audit_records_replica[1]', T,
                          'security_service', 'audit_record_9', 'security_audit_records', None, (),
                          {'resource_id': 'audit_record_9', 'subject_reference': SUBJECT,
                           'retention_until': '2030-01-01T00:00:00Z'}, 'sql', 'replica')
    assert decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
                  extra=[replica]).condition_outcome == TRUE
    from dataclasses import replace
    foreign = replace(replica, raw_fields=dict(replica.raw_fields, subject_reference='user_9002'))
    assert decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
                  extra=[foreign]).condition_outcome == UNKNOWN


def test_historical_identifiers_respect_audit_cutoff():
    old_email = 'old.address@example.com'
    history = resolution().history + (IdentityValue('email', old_email, old_email, 'synthetic_audit'),)
    with_history = Resolution('synthetic_case', T, SUBJECT, (SUBJECT,), 'resolved', {'email': SUBJECT_EMAIL}, history)
    term = retention_term({'customer_email': old_email})
    ctx = Context([obs({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9'), term], RULES)
    latest = {'system_id': 'security_service', 'resource_id': 'audit_record_9', 'topology': 'service',
              'state': 'PRESENT', 'supported': True, 'explanation': 'synthetic',
              'evidence_id': 'synthetic_evidence', 'locator': '$.records[0]'}
    # Known by the cutoff: the record is the subject's.
    assert decide_copy(ctx, latest, [latest], with_history, subject_from(with_history)).condition_outcome == TRUE
    # Not part of the cutoff-time identity view (e.g. acquired later): another person.
    res = resolution()
    assert decide_copy(ctx, latest, [latest], res, subject_from(res)).condition_outcome == UNKNOWN
    # Evidence captured after audit_at never counts, even for the subject.
    late = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT',
                  extra=[retention_term({'subject_reference': SUBJECT}, captured='2026-12-01T00:00:00Z')])
    assert late.condition_outcome == UNKNOWN


def test_other_persons_record_cannot_change_policy_decision():
    base = decide({'audience_cohort': 'x', 'email': SUBJECT_EMAIL}, 'analytics_platform', 'analytics_9', 'PRESENT')
    decoy = obs({'email_opt_in': 'true', 'email': OTHER_EMAIL}, 'analytics_platform', 'analytics_9',
                evidence='synthetic_decoy')
    contaminated = decide({'audience_cohort': 'x', 'email': SUBJECT_EMAIL}, 'analytics_platform', 'analytics_9',
                          'PRESENT', extra=[decoy])
    keys = ('category', 'rule_id', 'condition_outcome', 'effective_action', 'compliance', 'obligations')
    assert [getattr(base, k) for k in keys] == [getattr(contaminated, k) for k in keys]
    assert base.category == 'ANALYTICS_PROFILE'


def test_document_term_for_another_subject_is_ignored():
    lines = ['Event reference audit_record_9', 'subject reference user_9002', 'retain until 25 Aug 2027 04 03 UTC']
    docs = [Observation('synthetic_pdf', 'evidence/synthetic.pdf', f'line:{n}', T, None, None, None, None, (),
                        {'text': text}, 'pdf') for n, text in enumerate(lines, 1)]
    d = decide({'subject_reference': SUBJECT}, 'security_service', 'audit_record_9', 'PRESENT', extra=docs)
    assert d.condition_outcome == UNKNOWN
