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
from identity.retrieval import is_actor_field
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

    def holds(self, claim: tuple[str, str]) -> bool:
        kind, value = claim
        return {'email': value in self.emails, 'phone': value in self.phones,
                'email_hash': value in self.hashes, 'user_id': value == self.user_id}[kind]

    def attribution(self, claims) -> str:
        """SUBJECT if every named identifier is this subject's, FOREIGN if any is not."""
        if not claims: return 'UNATTRIBUTED'
        return 'SUBJECT' if all(self.holds(c) for c in claims) else 'FOREIGN'

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


def identity_claims(value, key='') -> set[tuple[str, str]]:
    """Explicit customer identifiers named by a record: emails, phones, hashes, user refs.

    Staff/actor fields (support agent, assignee, operator) are not customer
    identity, so they neither attribute a record to the subject nor to anyone else.
    """
    found = set()
    if is_actor_field(key):
        return found
    if isinstance(value, dict):
        for k, v in value.items(): found |= identity_claims(v, k)
    elif isinstance(value, list):
        for v in value: found |= identity_claims(v, key)
    elif isinstance(value, str) and value.strip():
        text, name = value.strip(), key.casefold()
        found |= {('email', e.casefold()) for e in EMAIL.findall(text)}
        found |= {('user_id', u) for u in USER.findall(text)}
        phones = PHONE.findall(text) or ([text] if 'phone' in name else [])
        found |= {('phone', ''.join(c for c in p if c.isdigit())) for p in phones
                  if sum(c.isdigit() for c in p) >= 7}
        if 'hash' in name or name == 'correlation_key':
            found |= {('email_hash', h) for h in HASH.findall(text)}
    return found


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
    # (activity_id, event_type, target_system, reported_result, event_time) on this
    # system/resource, admissible at audit_at: operation claims, never state proof.
    operations: tuple[tuple[str, str, str, str, str], ...] = ()
    # Values that co-occur with this subject's direct identifiers in an
    # admissible record (candidate re-identification keys).
    link_keys: frozenset[str] = frozenset()


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
            # Redacted content is not observed content: it can show no context either way.
            if not _nonnull(text) or str(text).strip() in config['redaction_markers']: continue
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


def _leaves(value, name=None, path=''):
    """(path, leaf field name, scalar) for every scalar in nested dicts/lists.

    A list item keeps the field name of its list, and an embedded JSON record
    string (``record_json``) is read as the record it carries.
    """
    if isinstance(value, str) and name == 'record_json':
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, dict):
        for key, item in sorted(value.items(), key=lambda kv: str(kv[0])):
            yield from _leaves(item, str(key), f'{path}.{key}' if path else str(key))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _leaves(item, name, f'{path}[{i}]')
    else:
        yield path, name, value


def _named(leaf, names) -> bool:
    return leaf is not None and (leaf in names or any(leaf.endswith('_' + n) for n in names))


def _removed(fields: dict, config: dict) -> tuple[int, int]:
    """(explicitly removed, still populated) direct identifier / stable reference
    fields, at any nesting depth."""
    names = set(config['identifier_fields']) | set(config['stable_reference_fields'])
    markers = set(config['redaction_markers'])
    removed = populated = 0
    for _, leaf, value in _leaves(fields):
        if leaf not in names: continue
        if not _nonnull(value) or str(value).strip() in markers: removed += 1
        else: populated += 1
    return removed, populated


def indirect_identifiers(fields: dict, config: dict) -> list[tuple[str, str]]:
    """Populated indirect identifiers (quasi-identifiers / linkage keys) at any
    nesting depth, as (path, value).

    Only fields named as (or suffixed by) a configured indirect identifier
    count, and only text or integer values: booleans, floats and unnamed
    numbers (metrics, counts, amounts) are never treated as identities.
    """
    names = set(config['anonymization']['indirect_identifier_fields'])
    markers = set(config['redaction_markers'])
    found = []
    for path, leaf, value in _leaves(fields):
        if not _named(leaf, names) or isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        if _nonnull(value) and str(value).strip() and str(value).strip() not in markers:
            found.append((path, str(value).strip()))
    return found


_indirect = indirect_identifiers


def anonymization_state(d: Dossier, config: dict) -> tuple[str, str, tuple[str, ...]]:
    """Classify the state-establishing copy for Rule 07/08 (F-02).

    Returns (state, reason, citations) with state one of:

    * DIRECT_EXPOSED: a direct identifier or stable reference is still populated.
    * INDIRECT_LINKED: an indirect identifier whose value co-occurs with this
      subject's direct identifiers in another admissible record (a link key).
    * INDIRECT_PRESENT: an indirect identifier remains; whether it re-links is not shown.
    * DIRECT_REMOVED: identifier columns explicitly emptied, no indirect identifier,
      but no independent evidence of an irreversible anonymization operation.
    * NOT_DISPLAYED: no identifier columns shown at all (absence is not removal).
    * ANONYMIZATION_EVIDENCED: identifiers removed, no indirect identifier or
      later identifying copy, and an ANONYMIZE_RECORD operation on this system
      and resource that the source read independently post-dates.
    * UNRESOLVED: no state-establishing field set.

    Explicitly null identifier columns alone are DIRECT_REMOVED, never
    anonymized: the record keeps its resource key, which earlier copies and
    backups may still join to the subject (pseudonymisation, not anonymity).
    """
    r = d.current
    if r is None:
        return 'UNRESOLVED', 'no field-level evidence of identifiers or their removal', ()
    permitted = tuple(config['permitted_fields'].get(d.category, ()))
    exposed = exposed_fields(r.fields, d.subject, config, permitted)
    if exposed:
        return 'DIRECT_EXPOSED', 'linkable via ' + ','.join(exposed), _cite(r)
    indirect = _indirect(r.fields, config)
    linked = [n for n, v in indirect if d.link_keys and v in d.link_keys]
    if linked:
        return ('INDIRECT_LINKED', 'linkable via indirect identifier(s) ' + ','.join(linked) +
                ' that co-occur with the subject\'s identifiers in another record', _cite(r))
    if indirect:
        return ('INDIRECT_PRESENT', 'indirect identifier(s) ' + ','.join(n for n, _ in indirect) +
                ' remain; re-identification neither shown nor excluded', _cite(r))
    removed, _ = _removed(r.fields, config)
    if not removed:
        return 'NOT_DISPLAYED', 'no direct identifier displayed; absence of a column is not removal', _cite(r)
    observed = parse_time(r.captured_at)
    later = [x for x in d.records if x is not r and (x.evidence_id, x.locator) != (r.evidence_id, r.locator)
             and parse_time(x.captured_at) >= observed
             and exposed_fields(x.fields, d.subject, config, permitted)]
    if later:
        return ('DIRECT_REMOVED', 'resource key still joined to subject identifiers in a copy observed '
                'at or after this one', _cite(r) + _cite(later[0]))
    accepted = set(config['anonymization']['operation_types'])
    ops = [o for o in d.operations if o[1] in accepted and o[3] in config['anonymization']['reported_results']
           and parse_time(o[4]) <= observed]
    if not ops:
        return ('DIRECT_REMOVED', 'identifier columns explicitly null, but no anonymization operation that '
                'the source read post-dates; null columns are not proof of irreversible unlinking', _cite(r))
    newest = max(ops, key=lambda o: (parse_time(o[4]), o[0]))
    # Records naming the subject observed after the operation re-link the key.
    relinked = [x for x in d.records if parse_time(x.captured_at) > parse_time(newest[4])
                and exposed_fields(x.fields, d.subject, config, permitted)]
    if relinked:
        return ('DIRECT_REMOVED', 'a copy naming the subject was observed after the anonymization operation',
                _cite(r) + _cite(relinked[0]))
    return ('ANONYMIZATION_EVIDENCED', f'{newest[1]} {newest[0]} at {newest[4]} followed by a source read '
            'with identifier columns removed and no indirect identifier', _cite(r) + (newest[0],))


ANONYMIZATION_OUTCOME = {'DIRECT_EXPOSED': TRUE, 'INDIRECT_LINKED': TRUE, 'INDIRECT_PRESENT': UNKNOWN,
                         'DIRECT_REMOVED': UNKNOWN, 'NOT_DISPLAYED': UNKNOWN, 'UNRESOLVED': UNKNOWN,
                         'ANONYMIZATION_EVIDENCED': FALSE}


def still_attributable(d: Dossier, config: dict) -> ConditionResult:
    # Only the state-establishing field set counts: older copies predate treatment.
    state, reason, cited = anonymization_state(d, config)
    return ConditionResult(ANONYMIZATION_OUTCOME[state], f'{state}: {reason}', cited)


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
            block = []
            for follow in lines[i + 1:]:
                if re.search(r'\b(audit|record)_\w*\d+\b', follow) and 'reference' in follow.casefold():
                    break
                block.append(follow)
            claims = set().union(*(identity_claims(t) for t in [line, *block]))
            # A document term counts only when its block itself names this subject.
            if d.subject.attribution(claims) != 'SUBJECT': continue
            for follow in block:
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
    # No period is supplied for this record. Owner policy decision (final sprint):
    # deletion_rules.csv gives SECURITY_AUDIT_LOG no DELETE (or any other) rule, so
    # the policy never authorizes removing an observed security audit record; with
    # 'retain_observed_without_period' it is preserved (RETAIN, verified PRESENT).
    # No retention period is invented: an expired period above stays FALSE, and
    # a record with no admissible field evidence stays UNKNOWN.
    if config.get('retention_without_period') == 'retain_observed_without_period' and d.current is not None:
        return ConditionResult(TRUE, 'no supplied retention period; the policy has no deletion basis for this '
                               'category, so the observed record is preserved', _cite(d.current))
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
