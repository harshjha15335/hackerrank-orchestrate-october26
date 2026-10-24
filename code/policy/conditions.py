"""Three-valued predicates for deletion_rules.csv conditions.

Predicates never see rule text. They are bound to a condition by the SHA-256 of
its wording in condition_bindings.json, so editing a condition in the CSV
unbinds it (UNKNOWN) instead of silently reusing a stale interpretation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ingest.evidence import EMAIL, PHONE, USER, ExtractionError, parse_time
from state.engine import parse_source_bool

TRUE, FALSE, UNKNOWN = 'TRUE', 'FALSE', 'UNKNOWN'
NULLISH = (None, '', 'null', 'none', 'None')
CONFIG = Path(__file__).with_name('condition_bindings.json')
HASH = re.compile(r'\b[0-9a-f]{64}\b')
PDF_DATE = re.compile(r'(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})(?:\s+(\d{2})\s+(\d{2}))?')
MONTHS = {m: i for i, m in enumerate(('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul',
                                      'Aug', 'Sep', 'Oct', 'Nov', 'Dec'), 1)}


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass(frozen=True)
class Subject:
    user_id: str | None
    emails: frozenset[str]
    phones: frozenset[str]
    hashes: frozenset[str]

    def owns(self, value: str) -> bool:
        text = str(value)
        if self.user_id and text == self.user_id: return True
        if any(e.casefold() in self.emails for e in EMAIL.findall(text)): return True
        if any(''.join(c for c in p if c.isdigit()) in self.phones for p in PHONE.findall(text)): return True
        return any(h in self.hashes for h in HASH.findall(text))

    def mentioned_in(self, value: str) -> bool:
        text = str(value)
        lowered = text.casefold()
        digits = ''.join(c for c in text if c.isdigit())
        return (any(e in lowered for e in self.emails) or any(h in text for h in self.hashes)
                or any(p and len(p) >= 7 and p in digits for p in self.phones)
                or bool(self.user_id and re.search(rf'\b{re.escape(self.user_id)}\b', text)))


def subject_from(resolution) -> Subject:
    values = {'email': set(), 'phone': set(), 'email_hash': set()}
    for item in resolution.history:
        if item.normalized: values[item.field].add(item.normalized)
    for name, value in (resolution.current_at_cutoff or {}).items():
        if value and name in values:
            values[name].add(value.casefold() if name == 'email' else
                             ''.join(c for c in value if c.isdigit()) if name == 'phone' else value)
    return Subject(resolution.user_id, frozenset(values['email']), frozenset(values['phone']),
                   frozenset(values['email_hash']))


@dataclass(frozen=True)
class Record:
    """One observed field set for the resource, with provenance."""
    evidence_id: str
    locator: str
    captured_at: str
    fields: dict
    subject_linked: bool


@dataclass
class Dossier:
    category: str
    state: str
    audit_at: str
    subject: Subject
    current: Record | None         # field set that established the latest M4 state
    records: list[Record]          # every same-resource field set, latest first
    documents: list[tuple[str, list[str]]] = field(default_factory=list)
    resource_id: str | None = None


@dataclass(frozen=True)
class ConditionResult:
    outcome: str
    reason: str
    evidence: tuple[str, ...] = ()


def _values(record: Record, names) -> list:
    return [record.fields[n] for n in names if n in record.fields]


def _nonnull(value) -> bool:
    return value not in NULLISH and not (isinstance(value, str) and value.strip() in NULLISH)


def _cite(record: Record) -> tuple[str, ...]:
    return (f'{record.evidence_id}:{record.locator}',)


def exposed_fields(fields: dict, subject: Subject, config: dict, permitted=()) -> tuple[str, ...]:
    """Fields still exposing a direct identifier; permitted stable references excluded."""
    markers = set(config['redaction_markers'])
    exposed = []
    for name, value in sorted(fields.items()):
        if (name in permitted or name in config['query_context_fields'] or
                name in ('resource_id', 'parsed_record', 'record_json', 'text')):
            continue
        if isinstance(value, (dict, list)):
            nested = value if isinstance(value, dict) else {f'{name}[{i}]': v for i, v in enumerate(value)}
            exposed.extend(f'{name}.{n}' for n in exposed_fields(nested, subject, config, permitted))
            continue
        if not _nonnull(value) or str(value).strip() in markers:
            continue
        if name in config['identifier_fields']:
            exposed.append(name)
        elif name in config['stable_reference_fields'] and name not in permitted:
            exposed.append(name)
        elif isinstance(value, str) and (subject.mentioned_in(value) or EMAIL.search(value)):
            exposed.append(name)
    return tuple(exposed)


def explicit_identifier_nulls(fields: dict, config: dict) -> int:
    names = set(config['identifier_fields']) | set(config['stable_reference_fields'])
    return sum(1 for n, v in fields.items() if n in names and not _nonnull(v))


# --- predicates -------------------------------------------------------------

def shared_support_context(d: Dossier, config: dict) -> ConditionResult:
    patterns = [re.compile(p, re.I) for p in config['shared_context_patterns']]
    saw_content = None
    for r in d.records:
        for name in config['shared_context_fields']:
            if _nonnull(r.fields.get(name)):
                return ConditionResult(TRUE, f'shared context field {name}', _cite(r))
        for name in config['content_fields']:
            text = r.fields.get(name)
            if not _nonnull(text): continue
            saw_content = saw_content or r
            if any(p.search(str(text)) for p in patterns):
                return ConditionResult(TRUE, f'{name} carries order/agent/support context', _cite(r))
    if saw_content:
        return ConditionResult(FALSE, 'conversation content observed without shared context', _cite(saw_content))
    return ConditionResult(UNKNOWN, 'no conversation content or context fields observed')


def attachment_subject_only(d: Dossier, config: dict) -> ConditionResult:
    owners, foreign, cited = set(), set(), None
    for r in d.records:
        for name, value in r.fields.items():
            if name in ('resource_id', 'text', 'parsed_record'): continue
            if not isinstance(value, str): continue
            for email in EMAIL.findall(value):
                cited = cited or r
                (owners if d.subject.owns(email) else foreign).add(email.casefold())
            if name in config['stable_reference_fields'] and USER.fullmatch(value.strip()):
                cited = cited or r
                (owners if d.subject.owns(value.strip()) else foreign).add(value.strip())
    if foreign:
        return ConditionResult(FALSE, f'{len(foreign)} other person identifier(s) on attachment', _cite(cited))
    if owners:
        return ConditionResult(TRUE, 'every identified owner/uploader is the deletion subject', _cite(cited))
    return ConditionResult(UNKNOWN, 'attachment ownership not observed')


def still_attributable(d: Dossier, config: dict) -> ConditionResult:
    permitted = tuple(config['permitted_fields'].get(d.category, ()))
    content = config['attribute_fields']['analytics_content']
    # Only the state-establishing field set counts: older copies predate treatment.
    current = [d.current] if d.current else []
    for r in current:
        exposed = exposed_fields(r.fields, d.subject, config, permitted)
        if exposed:
            return ConditionResult(TRUE, 'linkable via ' + ','.join(exposed), _cite(r))
    # Anonymity needs positive evidence: retained analytic content alongside
    # explicitly null identifier columns, not merely missing fields.
    for r in current:
        if (any(_nonnull(v) for v in _values(r, content)) and
                explicit_identifier_nulls(r.fields, config) >= 2):
            return ConditionResult(FALSE, 'analytic content retained with explicit null identifiers', _cite(r))
    return ConditionResult(UNKNOWN, 'no field-level evidence of identifiers or their removal')


def contains_email_address(d: Dossier, config: dict) -> ConditionResult:
    seen = None
    for r in [d.current] if d.current else []:
        for name, value in r.fields.items():
            if isinstance(value, str) and EMAIL.search(value):
                return ConditionResult(TRUE, f'email address in {name}', _cite(r))
        if any(_nonnull(v) for k, v in r.fields.items() if k != 'resource_id'):
            seen = seen or r
    if seen:
        return ConditionResult(FALSE, 'log fields observed without an email address', _cite(seen))
    return ConditionResult(UNKNOWN, 'no log content observed')


def _dated(value) -> datetime | None:
    try:
        return parse_time(value) if isinstance(value, str) else None
    except ExtractionError:
        return None


def _document_retention(d: Dossier) -> tuple[datetime, str] | None:
    """Retain-until stated in a document block naming this resource."""
    for citation, lines in d.documents:
        for i, line in enumerate(lines):
            if not d.resource_id or not re.search(rf'\b{re.escape(d.resource_id)}\b', line): continue
            for follow in lines[i + 1:]:
                if re.search(r'\b(audit|record)_\w*\d+\b', follow) and 'reference' in follow.casefold():
                    break
                if 'retain until' in follow.casefold():
                    m = PDF_DATE.search(follow.split('retain until', 1)[-1])
                    if m:
                        day, mon, year, hh, mm = m.groups()
                        when = datetime.fromisoformat(f'{year}-{MONTHS[mon]:02d}-{int(day):02d}T'
                                                      f'{hh or "00"}:{mm or "00"}:00+00:00')
                        return when, citation
    return None


def within_retention_period(d: Dossier, config: dict) -> ConditionResult:
    cutoff = parse_time(d.audit_at)
    names = config['attribute_fields']['retention_until']
    for r in d.records:
        for value in _values(r, names):
            until = _dated(value)
            if until is None: continue
            if until >= cutoff:
                return ConditionResult(TRUE, f'retention until {value} covers audit_at', _cite(r))
            return ConditionResult(FALSE, f'retention until {value} expired by audit_at', _cite(r))
    found = _document_retention(d)
    if found:
        until, citation = found
        outcome = TRUE if until >= cutoff else FALSE
        return ConditionResult(outcome, f'document retain-until {until.isoformat()}', (citation,))
    return ConditionResult(UNKNOWN, 'no supplied retention period for this record')


def legal_hold_active(d: Dossier, config: dict) -> ConditionResult:
    cutoff = parse_time(d.audit_at)
    attrs = config['attribute_fields']
    for r in d.records:
        for value in _values(r, attrs['hold_until']):
            until = _dated(value)
            if until is None: continue
            if not any(_nonnull(v) for v in _values(r, attrs['hold_basis'])):
                return ConditionResult(UNKNOWN, 'hold end date without a supplied hold basis', _cite(r))
            if until >= cutoff:
                return ConditionResult(TRUE, f'hold retained until {value}', _cite(r))
            return ConditionResult(FALSE, f'hold ended {value} before audit_at', _cite(r))
    return ConditionResult(UNKNOWN, 'no supplied legal hold term')


def restore_access_blockable(d: Dossier, config: dict) -> ConditionResult:
    if d.state in ('RESTORE_ENABLED', 'RESTORE_BLOCKED'):
        return ConditionResult(TRUE, f'validated restore control observed ({d.state})')
    for r in d.records:
        for value in _values(r, config['attribute_fields']['restore_flag']):
            if parse_source_bool(value) is not None:
                return ConditionResult(TRUE, 'explicit restore_allowed control', _cite(r))
    return ConditionResult(UNKNOWN, 'no explicit restore access control observed')


def deleted_account_reference_only(d: Dossier, config: dict) -> ConditionResult:
    for r in d.records:
        statuses = [v for v in _values(r, config['attribute_fields']['account_status']) if _nonnull(v)]
        if not statuses: continue
        if str(statuses[0]).strip().upper() != 'DELETED':
            return ConditionResult(FALSE, f'account_status={statuses[0]}', _cite(r))
        refs = [v for v in _values(r, config['permitted_fields']['ACCOUNT_TOMBSTONE'])
                if isinstance(v, str) and USER.fullmatch(v.strip())]
        if refs:
            return ConditionResult(TRUE, 'deleted account keeps a stable internal user reference', _cite(r))
        return ConditionResult(UNKNOWN, 'deleted account without a stable internal reference', _cite(r))
    return ConditionResult(UNKNOWN, 'account status not observed')


PREDICATES = {f.__name__: f for f in (
    shared_support_context, attachment_subject_only, still_attributable, contains_email_address,
    within_retention_period, legal_hold_active, restore_access_blockable, deleted_account_reference_only)}


def evaluate(rule, dossier: Dossier, config: dict) -> tuple[ConditionResult, dict | None]:
    if rule.unconditional:
        return ConditionResult(TRUE, 'unconditional rule'), None
    binding = config['bindings'].get(rule.condition_fingerprint)
    if not binding or binding['predicate'] not in PREDICATES:
        return ConditionResult(UNKNOWN, 'condition wording has no bound predicate'), None
    return PREDICATES[binding['predicate']](dossier, config), binding
