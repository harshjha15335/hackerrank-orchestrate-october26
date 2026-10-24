"""Strict, dependency-free October output contract. Never reads sample answers."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

COLUMNS = ('case_id', 'deletion_status', 'steps_json')
FIELDS = ('step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id')
# Table order in problem_statement.md is normative, not alphabetical order.
OPERATIONS = {
    'FINDING': {'REPORT_REMAINING_RECORD': 'PRESENT', 'REPORT_EXPOSED_PII': 'PRESENT',
                'REPORT_ACTIVE_DATA_FLOW': 'ACTIVE', 'REPORT_RESTORE_RISK': 'ACTIVE'},
    'REMEDIATION': {'DISABLE_DATA_FLOW': 'DISABLED', 'BLOCK_RESTORE': 'BLOCKED',
                    'DELETE_RECORD': 'ABSENT', 'REDACT_RECORD': 'REDACTED',
                    'ANONYMIZE_RECORD': 'ANONYMIZED'},
    'VERIFICATION': {'VERIFY_RECORD_ABSENT': 'ABSENT', 'VERIFY_RECORD_PRESENT': 'PRESENT',
                     'VERIFY_RECORD_REDACTED': 'REDACTED', 'VERIFY_RECORD_ANONYMIZED': 'ANONYMIZED',
                     'VERIFY_DATA_FLOW_DISABLED': 'DISABLED', 'VERIFY_RESTORE_BLOCKED': 'BLOCKED'},
}
VERIFY = dict(zip(OPERATIONS['REMEDIATION'], (
    'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RESTORE_BLOCKED', 'VERIFY_RECORD_ABSENT',
    'VERIFY_RECORD_REDACTED', 'VERIFY_RECORD_ANONYMIZED')))
FINDING_ACTIONS = {
    'REPORT_REMAINING_RECORD': {'DELETE_RECORD'},
    'REPORT_EXPOSED_PII': {'REDACT_RECORD', 'ANONYMIZE_RECORD'},
    'REPORT_ACTIVE_DATA_FLOW': {'DISABLE_DATA_FLOW'},
    'REPORT_RESTORE_RISK': {'BLOCK_RESTORE'},
}


class ContractError(ValueError):
    """Malformed input, with a diagnostic suitable for a CLI."""


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ContractError('timestamp must include timezone')
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def _constant(value):
    raise ContractError(f'invalid JSON constant: {value}')


def read_output(path: Path) -> list[dict]:
    """Parse exact CSV and JSON; semantic validation is separate for diagnostics."""
    try:
        with Path(path).open(encoding='utf-8', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            if next(reader, None) != list(COLUMNS):
                raise ContractError(f'CSV header must be exactly {list(COLUMNS)}')
            rows = []
            for number, cells in enumerate(reader, 2):
                if len(cells) != 3:
                    raise ContractError(f'CSV row {number}: expected 3 columns, got {len(cells)}')
                row = dict(zip(COLUMNS, cells))
                try:
                    row['steps_json'] = json.loads(cells[2], object_pairs_hook=_object,
                                                   parse_constant=_constant)
                except (ValueError, RecursionError) as exc:
                    raise ContractError(f'CSV row {number}: invalid steps_json: {exc}') from exc
                rows.append(row)
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ContractError(str(exc)) from exc


@dataclass
class ValidationResult:
    row_count: int
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def step_shape(step) -> bool:
    return (isinstance(step, dict) and set(step) == set(FIELDS)
            and type(step['step_no']) is int
            and all(isinstance(step[k], str) for k in FIELDS[1:]))


def validate_rows(rows: list[dict], requests: dict[str, datetime],
                  evidence: dict[str, datetime], allow_unproven_incomplete: bool = False) -> ValidationResult:
    """Validate all cases and structurally detectable plan coverage; never repairs output.

    With ``allow_unproven_incomplete`` (M7 production output), an INCOMPLETE
    case whose only problem is unresolved uncertainty may carry no finding:
    either no steps at all or future verification steps only. Any finding
    still requires remediation and verification.
    """
    result = ValidationResult(len(rows))
    errors = result.errors
    ids = [r['case_id'] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append('case_id: duplicated cases')
    if ids != sorted(ids):
        errors.append('case_id: cases must be sorted ascending')
    for label, values in [('missing', set(requests) - set(ids)), ('unexpected', set(ids) - set(requests))]:
        if values:
            errors.append(f'{label} cases: {", ".join(sorted(values))}')
    for row in rows:
        case = row['case_id']
        status, steps = row['deletion_status'], row['steps_json']
        def fail(message):
            errors.append(f'{case}: {message}')
        if status not in {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}:
            fail('invalid deletion_status')
        if not isinstance(steps, list):
            fail('steps_json must be an array')
            continue
        if status == 'NOT_APPLICABLE' and steps:
            fail('NOT_APPLICABLE must have zero steps')
        if status == 'COMPLETE' and not steps or status == 'INCOMPLETE' and not steps and not allow_unproven_incomplete:
            fail(f'{status} requires nonempty steps')
        keys = []
        typed = []
        for index, step in enumerate(steps, 1):
            if not step_shape(step):
                fail(f'step {index}: expected exactly seven fields {list(FIELDS)} with integer step_no and string values')
                continue
            typed.append(step)
            phase, op = step['phase'], step['operation']
            if step['step_no'] != index:
                fail(f'step {index}: step_no must be consecutive starting at 1')
            if not step['system_id'].strip() or not step['resource_id'].strip():
                fail(f'step {index}: system_id and resource_id must be nonempty')
            if phase not in OPERATIONS or op not in OPERATIONS[phase]:
                fail(f'step {index}: invalid phase/operation combination')
            else:
                if step['state'] != OPERATIONS[phase][op]:
                    fail(f'step {index}: incorrect operation/state pair')
                keys.append((list(OPERATIONS).index(phase), list(OPERATIONS[phase]).index(op),
                             step['system_id'], step['resource_id']))
            if status == 'COMPLETE' and phase != 'VERIFICATION':
                fail(f'step {index}: COMPLETE permits only VERIFICATION')
            needs_evidence = phase == 'FINDING' or (status == 'COMPLETE' and phase == 'VERIFICATION')
            citation = step['evidence_id']
            if needs_evidence:
                if not citation.strip():
                    fail(f'step {index}: nonempty evidence_id required')
                elif citation not in evidence:
                    fail(f'step {index}: unknown evidence_id {citation}')
                elif case in requests and evidence[citation] > requests[case]:
                    fail(f'step {index}: evidence_id is later than audit_at')
            elif phase in {'REMEDIATION', 'VERIFICATION'} and citation != '':
                fail(f'step {index}: proposed remediation/future verification requires empty evidence_id')
        if keys != sorted(keys):
            fail('incorrect phase/operation/system_id/resource_id ordering')
        if status == 'INCOMPLETE':
            phases = {s['phase'] for s in typed}
            unproven = allow_unproven_incomplete and 'FINDING' not in phases
            if unproven and 'REMEDIATION' in phases:
                fail('remediation without an evidenced finding')
            elif not unproven and phases != set(OPERATIONS):
                fail('INCOMPLETE requires FINDING, REMEDIATION and VERIFICATION phases')
            actual = {(s['operation'], s['system_id'], s['resource_id']) for s in typed}
            for step in typed:
                op, system, resource = step['operation'], step['system_id'], step['resource_id']
                if op in VERIFY and (VERIFY[op], system, resource) not in actual:
                    fail(f'missing verification {VERIFY[op]} for {system}/{resource}')
                if op in FINDING_ACTIONS and not any((action, system, resource) in actual for action in FINDING_ACTIONS[op]):
                    fail(f'missing remediation for {op} on {system}/{resource}')
    return result


def load_context(dataset: Path, mode: str) -> tuple[dict, dict]:
    if mode not in {'sample', 'full'}:
        raise ContractError('mode must be sample or full')
    name = 'sample_deletion_requests.csv' if mode == 'sample' else 'deletion_requests.csv'
    requests = {}
    with (dataset / name).open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['case_id'] in requests:
                raise ContractError('duplicate case in request data')
            requests[row['case_id']] = timestamp(row['audit_at'])
    evidence = {}
    for name, key, time in [('evidence_files.csv', 'file_id', 'captured_at'),
                             ('system_activity.csv', 'activity_id', 'event_time'),
                             ('user_audit_log.csv', 'audit_id', 'event_time')]:
        with (dataset / name).open(encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                if row[key] in evidence:
                    raise ContractError('duplicate evidence ID in context')
                evidence[row[key]] = timestamp(row[time])
    return requests, evidence


def validate_file(path: Path, dataset: Path, mode: str) -> ValidationResult:
    try:
        requests, evidence = load_context(dataset, mode)
        return validate_rows(read_output(path), requests, evidence)
    except (ContractError, OSError, ValueError, KeyError) as exc:
        return ValidationResult(0, [str(exc)])
