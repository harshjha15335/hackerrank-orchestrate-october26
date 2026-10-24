"""Offline tests; all negative fixtures are synthetic, never mutated official files."""
import copy
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.contract import (COLUMNS, FIELDS, OPERATIONS, ContractError, load_context,
                                 read_output, timestamp, validate_file, validate_rows)
from evaluation.scorer import evaluate_sample, score_rows

ROOT = Path(__file__).resolve().parents[3]
NOW = timestamp('2026-01-02T00:00:00Z')
REQUESTS = {'synthetic_case': NOW}
EVIDENCE = {'synthetic_evidence': NOW}


def step(op, evidence='', system='synthetic_system', resource='synthetic_resource'):
    phase = next(p for p, ops in OPERATIONS.items() if op in ops)
    return dict(zip(FIELDS, (1, phase, system, resource, op, OPERATIONS[phase][op], evidence)))


def row(status='INCOMPLETE'):
    if status == 'INCOMPLETE':
        steps = [step('REPORT_REMAINING_RECORD', 'synthetic_evidence'),
                 step('DELETE_RECORD'), step('VERIFY_RECORD_ABSENT')]
    elif status == 'COMPLETE':
        steps = [step('VERIFY_RECORD_ABSENT', 'synthetic_evidence')]
    else:
        steps = []
    for i, s in enumerate(steps, 1):
        s['step_no'] = i
    return {'case_id': 'synthetic_case', 'deletion_status': status, 'steps_json': steps}


def valid(rows):
    return validate_rows(rows, REQUESTS, EVIDENCE)


def write_csv(path, rows, header=COLUMNS):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(header)
        writer.writerows((r['case_id'], r['deletion_status'], json.dumps(r['steps_json'])) for r in rows)


@pytest.mark.parametrize('status', ['COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'])
def test_valid_statuses(status):
    assert valid([row(status)]).valid


@pytest.mark.parametrize('mutation,message', [
    ('missing_case', 'missing cases'), ('duplicate_case', 'duplicated cases'),
    ('extra_case', 'unexpected cases'), ('unsorted', 'sorted ascending'),
    ('status', 'invalid deletion_status'), ('not_array', 'must be an array'),
    ('not_object', 'exactly seven fields'), ('six_fields', 'exactly seven fields'),
    ('eight_fields', 'exactly seven fields'), ('bad_pair', 'operation/state'),
    ('phase_order', 'ordering'), ('operation_order', 'ordering'),
    ('system_order', 'ordering'), ('resource_order', 'ordering'),
    ('number', 'step_no'), ('bool_number', 'exactly seven fields'),
    ('string_number', 'exactly seven fields'), ('unknown_op', 'phase/operation'),
    ('wrong_phase', 'phase/operation'), ('unknown_phase', 'phase/operation'),
    ('empty_evidence', 'nonempty evidence'), ('unknown_evidence', 'unknown evidence'),
    ('future_evidence', 'later than audit_at'), ('complete_evidence', 'nonempty evidence'),
    ('remediation_evidence', 'requires empty evidence'), ('future_verification_evidence', 'requires empty evidence'),
    ('missing_verification', 'missing verification'), ('wrong_verification', 'missing verification'),
    ('missing_remediation', 'missing remediation'), ('missing_finding', 'requires FINDING'),
    ('complete_finding', 'only VERIFICATION'), ('empty_complete', 'requires nonempty'),
    ('empty_incomplete', 'requires nonempty'), ('nonempty_na', 'zero steps'),
    ('empty_system', 'must be nonempty'), ('empty_resource', 'must be nonempty'),
    ('bad_value_type', 'exactly seven fields'),
])
def test_mutations(mutation, message):
    r = row(); rows = [r]; s = r['steps_json']
    evidence = dict(EVIDENCE)
    if mutation == 'missing_case': rows = []
    elif mutation == 'duplicate_case': rows.append(copy.deepcopy(r))
    elif mutation == 'extra_case': rows.append(dict(r, case_id='unexpected_synthetic'))
    elif mutation == 'unsorted': rows.insert(0, dict(r, case_id='z_synthetic'))
    elif mutation == 'status': r['deletion_status'] = 'complete'
    elif mutation == 'not_array': r['steps_json'] = {}
    elif mutation == 'not_object': s[0] = []
    elif mutation == 'six_fields': del s[0]['state']
    elif mutation == 'eight_fields': s[0]['extra'] = 'no'
    elif mutation == 'bad_pair': s[0]['state'] = 'ABSENT'
    elif mutation == 'phase_order': s[0], s[1] = s[1], s[0]
    elif mutation == 'operation_order':
        s.insert(0, step('REPORT_ACTIVE_DATA_FLOW', 'synthetic_evidence'))
    elif mutation in ('system_order', 'resource_order'):
        field = 'system_id' if mutation == 'system_order' else 'resource_id'
        s.insert(1, copy.deepcopy(s[0])); s[0][field] = 'z_synthetic'; s[1][field] = 'a_synthetic'
    elif mutation == 'number': s[1]['step_no'] = 4
    elif mutation == 'bool_number': s[0]['step_no'] = True
    elif mutation == 'string_number': s[0]['step_no'] = '1'
    elif mutation == 'unknown_op': s[0]['operation'] = 'MADE_UP'
    elif mutation == 'wrong_phase': s[0]['phase'] = 'REMEDIATION'
    elif mutation == 'unknown_phase': s[0]['phase'] = 'MADE_UP'
    elif mutation == 'empty_evidence': s[0]['evidence_id'] = ' '
    elif mutation == 'unknown_evidence': s[0]['evidence_id'] = 'unlisted_synthetic'
    elif mutation == 'future_evidence': evidence['synthetic_evidence'] = timestamp('2026-01-03T00:00:00Z')
    elif mutation == 'complete_evidence': r = row('COMPLETE'); r['steps_json'][0]['evidence_id'] = ''; rows = [r]
    elif mutation == 'remediation_evidence': s[1]['evidence_id'] = 'synthetic_evidence'
    elif mutation == 'future_verification_evidence': s[2]['evidence_id'] = 'synthetic_evidence'
    elif mutation == 'missing_verification': s.pop()
    elif mutation == 'wrong_verification': s[2] = step('VERIFY_RECORD_PRESENT'); s[2]['step_no'] = 3
    elif mutation == 'missing_remediation': s.pop(1)
    elif mutation == 'missing_finding': s.pop(0)
    elif mutation == 'complete_finding': r['deletion_status'] = 'COMPLETE'
    elif mutation == 'empty_complete': r['deletion_status'] = 'COMPLETE'; s.clear()
    elif mutation == 'empty_incomplete': s.clear()
    elif mutation == 'nonempty_na': r['deletion_status'] = 'NOT_APPLICABLE'
    elif mutation == 'empty_system': s[0]['system_id'] = ' '
    elif mutation == 'empty_resource': s[0]['resource_id'] = ''
    elif mutation == 'bad_value_type': s[0]['evidence_id'] = 5
    result = validate_rows(rows, REQUESTS, evidence)
    assert not result.valid
    assert any(message in error for error in result.errors), result.errors


@pytest.mark.parametrize('op', list(OPERATIONS['REMEDIATION']))
def test_verification_coverage_all_remediations(op):
    r = row(); r['steps_json'][1] = step(op); r['steps_json'][1]['step_no'] = 2
    if op == 'DELETE_RECORD':
        r['steps_json'][2] = step('VERIFY_RECORD_PRESENT'); r['steps_json'][2]['step_no'] = 3
    result = valid([r])
    assert any('missing verification' in e for e in result.errors)


@pytest.mark.parametrize('payload', ['{', 'NaN', '[{"x":1,"x":2}]', 'null'])
def test_invalid_json_or_array(tmp_path, payload):
    path = tmp_path / 'bad.csv'
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(COLUMNS)
        writer.writerow(['synthetic_case', 'COMPLETE', payload])
    if payload == 'null':
        assert not valid(read_output(path)).valid
    else:
        with pytest.raises(ContractError, match='invalid steps_json'):
            read_output(path)


@pytest.mark.parametrize('header', [COLUMNS[::-1], (*COLUMNS, 'extra'), COLUMNS[:2]])
def test_exact_csv_header(tmp_path, header):
    path = tmp_path / 'bad.csv'; write_csv(path, [], header)
    with pytest.raises(ContractError, match='CSV header'):
        read_output(path)


@pytest.mark.parametrize('text', [
    'case_id,deletion_status,steps_json\nx,NOT_APPLICABLE,[],extra\n',
    'case_id,deletion_status,steps_json\nx,NOT_APPLICABLE\n',
    'case_id,deletion_status,steps_json\nx,COMPLETE,"unterminated\n',
])
def test_malformed_csv(tmp_path, text):
    path = tmp_path / 'bad.csv'; path.write_text(text)
    with pytest.raises(ContractError): read_output(path)


def test_csv_quoting_embedded_json_and_unicode(tmp_path):
    r = row('COMPLETE'); r['steps_json'][0]['resource_id'] = 'synthetic,"quoted"\n日本語'
    path = tmp_path / 'quoted.csv'; write_csv(path, [r])
    assert read_output(path) == [r]
    assert valid(read_output(path)).valid


def test_complete_allows_all_verification_operations():
    r = row('COMPLETE')
    r['steps_json'] = [step(op, 'synthetic_evidence') for op in OPERATIONS['VERIFICATION']]
    for i, s in enumerate(r['steps_json'], 1): s['step_no'] = i
    assert valid([r]).valid


def test_incomplete_allows_additional_retained_verification():
    r = row(); s = step('VERIFY_RECORD_PRESENT'); s['step_no'] = 4; r['steps_json'].append(s)
    assert valid([r]).valid


def test_official_samples_validate_and_self_score():
    before = hashlib.sha256((ROOT / 'dataset/sample_output.csv').read_bytes()).hexdigest()
    result = validate_file(ROOT / 'dataset/sample_output.csv', ROOT / 'dataset', 'sample')
    assert result.valid, result.errors
    assert result.row_count == 32
    requests, evidence = load_context(ROOT / 'dataset', 'sample')
    report = evaluate_sample(ROOT / 'dataset/sample_output.csv', ROOT / 'dataset', evidence, requests)
    assert [report[s]['case_count'] for s in ('all', 'dev', 'holdout')] == [32, 22, 10]
    for split in report.values():
        assert not split['mismatches']
        for name, value in split['metrics'].items():
            if name == 'matched_field_accuracy':
                assert all(m['value'] == 1 for m in value.values())
            else: assert value['value'] == 1, name
    assert hashlib.sha256((ROOT / 'dataset/sample_output.csv').read_bytes()).hexdigest() == before


def test_score_drop_step_denominators():
    gold = [row()]; pred = copy.deepcopy(gold); pred[0]['steps_json'].pop()
    result = score_rows(pred, gold)
    m = result['metrics']
    assert m['step_recall']['value'] == pytest.approx(2/3)
    assert m['step_precision']['value'] == 1
    assert m['step_f1']['value'] == pytest.approx(4/5)
    assert m['operation_accuracy']['denominator'] == 3
    assert m['step_count_accuracy']['value'] == 0
    assert result['mismatches'][0]['differences'][0]['position'] == 3


def test_score_swap_steps():
    gold = [row()]; pred = copy.deepcopy(gold)
    pred[0]['steps_json'][0], pred[0]['steps_json'][1] = pred[0]['steps_json'][1], pred[0]['steps_json'][0]
    m = score_rows(pred, gold)['metrics']
    assert m['step_f1']['value'] == 1
    assert m['sequence_accuracy']['value'] == 0
    assert m['normalised_kendall_tau']['value'] == pytest.approx(2/3)
    assert m['case_exact_match']['value'] == 0


def test_score_evidence_mutation():
    gold = [row()]; pred = copy.deepcopy(gold); pred[0]['steps_json'][0]['evidence_id'] = 'wrong_synthetic'
    m = score_rows(pred, gold, EVIDENCE, REQUESTS)['metrics']
    assert m['field_accuracy']['value'] == pytest.approx(20/21)
    assert m['evidence_id_accuracy']['value'] == pytest.approx(2/3)
    assert m['matched_field_accuracy']['evidence_id']['value'] == pytest.approx(2/3)
    assert m['evidence_validity_rate']['value'] == 0
    assert m['sequence_accuracy']['value'] == 1


@pytest.mark.parametrize('field', ['operation', 'system_id', 'resource_id', 'state', 'deletion_status'])
def test_score_field_sensitivity(field):
    gold = [row()]; pred = copy.deepcopy(gold)
    if field == 'deletion_status': pred[0][field] = 'COMPLETE'
    else: pred[0]['steps_json'][0][field] = 'wrong_synthetic'
    m = score_rows(pred, gold)['metrics']
    assert m['case_exact_match']['value'] == 0
    if field == 'deletion_status': assert m['status_accuracy']['value'] == 0
    elif field == 'state': assert m['matched_field_accuracy']['state']['value'] == pytest.approx(2/3)
    else: assert m[field + '_accuracy']['value'] == pytest.approx(2/3)


def test_score_case_alignment_and_missing_extra():
    gold = [row(), dict(row('NOT_APPLICABLE'), case_id='synthetic_two')]
    assert score_rows(gold[::-1], gold)['metrics']['case_exact_match']['value'] == 1
    missing = score_rows(gold[:1], gold)
    assert missing['metrics']['status_accuracy']['value'] == .5
    extra = gold + [dict(row('NOT_APPLICABLE'), case_id='synthetic_extra')]
    assert score_rows(extra, gold)['metrics']['case_exact_match']['value'] == pytest.approx(2/3)


def test_score_duplicates_are_not_collapsed():
    gold = [row()]; pred = copy.deepcopy(gold)
    pred[0]['steps_json'].append(copy.deepcopy(pred[0]['steps_json'][2]))
    assert score_rows(pred, gold)['metrics']['step_precision']['value'] == .75
    with pytest.raises(ContractError, match='duplicate case_id'): score_rows(gold * 2, gold)


def test_score_empty_conventions():
    m = score_rows([row('NOT_APPLICABLE')], [row('NOT_APPLICABLE')])['metrics']
    assert m['step_f1']['value'] == 1
    assert m['field_accuracy']['value'] == 1
    m = score_rows([], [row()])['metrics']
    assert m['step_recall']['value'] == 0
    assert m['field_accuracy']['value'] == 0


def test_cli_determinism_and_exit_codes(tmp_path):
    path = tmp_path / 'valid.csv'; write_csv(path, [row('NOT_APPLICABLE')])
    cmd = [sys.executable, str(ROOT / 'code/evaluation/main.py'), 'validate', str(path)]
    first = subprocess.run(cmd, capture_output=True)
    second = subprocess.run(cmd, capture_output=True)
    assert first.returncode == second.returncode == 1  # synthetic ID not in official requests
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)['validation']['errors']
    cmd[-1] = str(ROOT / 'dataset/sample_output.csv')
    assert subprocess.run(cmd, capture_output=True).returncode == 0


def test_full_stub_determinism_and_protected_paths(tmp_path):
    hashes = []
    root_output = ROOT / 'output.csv'
    original = root_output.read_bytes() if root_output.exists() else None
    for name in ('first.csv', 'second.csv'):
        path = tmp_path / name
        subprocess.run([sys.executable, str(ROOT / 'code/main.py'), '--output', str(path)], check=True)
        result = validate_file(path, ROOT / 'dataset', 'full')
        assert result.valid, result.errors
        assert result.row_count == 518
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1]
    for path in [root_output, ROOT / 'dataset/sample_output.csv', tmp_path / 'first.csv']:
        assert subprocess.run([sys.executable, str(ROOT / 'code/main.py'), '--output', str(path)], capture_output=True).returncode != 0
    assert (root_output.read_bytes() if root_output.exists() else None) == original
    assert not (ROOT / 'code/__init__.py').exists()


def test_production_does_not_load_gold():
    source = (ROOT / 'code/main.py').read_text()
    assert 'sample_output' not in source
    assert 'evaluation' not in source


def test_sample_full_modes_are_distinct():
    result = validate_file(ROOT / 'dataset/sample_output.csv', ROOT / 'dataset', 'full')
    assert not result.valid
    assert any('missing cases' in e for e in result.errors)
    with pytest.raises(ContractError, match='mode must be'):
        load_context(ROOT / 'dataset', 'unknown')


def test_missing_file_diagnostic(tmp_path):
    assert not validate_file(tmp_path / 'absent.csv', ROOT / 'dataset', 'sample').valid


def test_cli_score_deterministic_self_and_mismatch(tmp_path):
    cmd = [sys.executable, str(ROOT / 'code/evaluation/main.py'), 'score',
           str(ROOT / 'dataset/sample_output.csv')]
    a = subprocess.run(cmd, capture_output=True)
    b = subprocess.run(cmd, capture_output=True)
    assert a.returncode == b.returncode == 0
    assert a.stdout == b.stdout
    assert json.loads(a.stdout)['evaluation']['all']['metrics']['step_f1']['value'] == 1
    path = tmp_path / 'empty.csv'; write_csv(path, [])
    cmd[-1] = str(path)
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert len(report['evaluation']['all']['mismatches']) == 32
    assert report['evaluation']['all']['metrics']['status_accuracy']['value'] == 0


def test_cli_unparseable_json_is_failure(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('case_id,deletion_status,steps_json\nsynthetic_case,COMPLETE,{\n')
    result = subprocess.run([sys.executable, str(ROOT / 'code/evaluation/main.py'), 'score', str(path)], capture_output=True)
    assert result.returncode == 1
    assert 'scoring_error' in json.loads(result.stdout)


def test_no_official_answer_ids_in_python_sources():
    # Read gold only within evaluation, for the checkpoint's leakage audit.
    gold = read_output(ROOT / 'dataset/sample_output.csv')
    identifiers = {r['case_id'] for r in gold}
    for r in gold:
        for s in r['steps_json']:
            identifiers.update(s[f] for f in ('resource_id', 'evidence_id') if s[f])
    for path in (ROOT / 'code').rglob('*.py'):
        source = path.read_text()
        assert not any(value in source for value in identifiers), path


def test_evidence_validity_inclusive_timezone_boundary():
    evidence = {'synthetic_evidence': timestamp('2026-01-02T05:30:00+05:30')}
    assert validate_rows([row('COMPLETE')], REQUESTS, evidence).valid
    m = score_rows([row('COMPLETE')], [row('COMPLETE')], evidence, REQUESTS)['metrics']
    assert m['evidence_validity_rate']['value'] == 1


@pytest.mark.parametrize('bad', [True, 1.0, None])
def test_strict_step_number_types(bad):
    r = row(); r['steps_json'][0]['step_no'] = bad
    assert not valid([r]).valid


def test_timestamp_requires_timezone():
    with pytest.raises(ContractError, match='timezone'):
        timestamp('2026-01-02T00:00:00')
