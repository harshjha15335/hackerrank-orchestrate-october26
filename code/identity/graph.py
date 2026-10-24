"""Deterministic current/historical identity graph with case-time views."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ingest.evidence import normalized, parse_time

FIELDS = ('email', 'phone', 'email_hash')


def norm(field: str, value: str) -> str:
    value = (value or '').strip()
    if field == 'email': return value.casefold()
    if field == 'phone': return ''.join(c for c in value if c.isdigit())
    return value  # hashes are opaque; no guessed algorithm or case folding


@dataclass(frozen=True)
class IdentityValue:
    field: str
    original: str
    normalized: str
    source_id: str


@dataclass(frozen=True)
class Resolution:
    case_id: str
    audit_at: str
    user_id: str | None
    candidates: tuple[str, ...]
    status: str
    current_at_cutoff: dict[str, str | None]
    history: tuple[IdentityValue, ...]


class IdentityGraph:
    def __init__(self, dataset: Path):
        self.dataset = Path(dataset)
        with (self.dataset / 'user_identities.csv').open(newline='', encoding='utf-8') as f:
            self.users = {r['user_id']: r for r in csv.DictReader(f)}
        self.audit = {u: [] for u in self.users}
        with (self.dataset / 'user_audit_log.csv').open(newline='', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r['user_id'] not in self.audit: raise ValueError('audit references unknown user')
                if r['field_name'] in FIELDS: self.audit[r['user_id']].append(r)
        for events in self.audit.values():
            events.sort(key=lambda r: (parse_time(r['event_time']), r['audit_id']))

    def at(self, user_id: str, cutoff: str):
        point = parse_time(cutoff)
        user = self.users[user_id]
        current = {field: user[field] or None for field in FIELDS}
        # Reverse post-cutoff transitions. The old value existed just before
        # each change, while its new value must not leak into an earlier view.
        for change in reversed(self.audit[user_id]):
            if parse_time(change['event_time']) > point:
                current[change['field_name']] = change['old_value'] or None
        values = {}
        def add(field, value, source):
            if value:
                item = IdentityValue(field, value, norm(field, value), source)
                values[(field, value, source)] = item
        for field, value in current.items(): add(field, value, 'snapshot_or_reversed_history')
        for change in self.audit[user_id]:
            if parse_time(change['event_time']) <= point:
                for key in ('old_value', 'new_value'):
                    add(change['field_name'], change[key], change['audit_id'])
        return current, tuple(sorted(values.values(), key=lambda v: (v.field, v.normalized, v.original, v.source_id)))

    def resolve(self, case: dict) -> Resolution:
        address = norm('email', case['email'])
        matches = []
        for user_id in sorted(self.users):
            _, history = self.at(user_id, case['audit_at'])
            if address and any(v.field == 'email' and v.normalized == address for v in history):
                matches.append(user_id)
        if len(matches) == 1:
            current, history = self.at(matches[0], case['audit_at'])
            return Resolution(case['case_id'], case['audit_at'], matches[0], tuple(matches),
                              'resolved', current, history)
        return Resolution(case['case_id'], case['audit_at'], None, tuple(matches),
                          'ambiguous' if matches else 'unresolved', {}, ())

    def requests(self, sample=False):
        name = 'sample_deletion_requests.csv' if sample else 'deletion_requests.csv'
        with (self.dataset / name).open(newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
