"""Exact identifier index; returns all candidates with source context."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ingest.evidence import EMAIL, PHONE, USER, Observation, parse_time
from .graph import Resolution, norm

DIRECT = {'user_id', 'subject_reference', 'customer_reference', 'email', 'email_hash',
          'phone', 'owner_email', 'owner_phone', 'requester_email', 'requester_phone',
          'customer_email', 'lookup_key', 'correlation_key', 'old_value', 'new_value'}
HASH = re.compile(r'[0-9a-fA-F]{64}\Z')


def direct_identifiers(value, key=''):
    found = set()
    if isinstance(value, dict):
        for k, v in value.items(): found.update(direct_identifiers(v, k))
    elif isinstance(value, list):
        for v in value: found.update(direct_identifiers(v, key))
    elif isinstance(value, str) and (key in DIRECT or key.endswith(('_email', '_phone', '_hash'))):
        for email in EMAIL.findall(value): found.add(('email', norm('email', email)))
        for user in USER.findall(value): found.add(('user_id', user))
        for phone in PHONE.findall(value): found.add(('phone', norm('phone', phone)))
        if 'hash' in key and value: found.add(('email_hash', value))
        if key == 'correlation_key' and HASH.fullmatch(value): found.add(('email_hash', value))
    return found


@dataclass(frozen=True)
class Hit:
    observation: Observation
    matched: tuple[tuple[str, str], ...]
    strength: str


class EvidenceIndex:
    def __init__(self, observations: list[Observation]):
        self.observations = observations
        self.postings = {}
        self.groups = defaultdict(set)
        for position, observation in enumerate(observations):
            raw = observation.raw_fields
            if observation.source_type == 'log' and raw.get('trace_id'):
                self.groups[('trace', observation.evidence_id, raw['trace_id'])].add(position)
            if observation.source_type == 'json':
                match = re.match(r'(\$\.service_exports)\.[^.]+\.[^[]+\[(\d+)\]', observation.locator)
                if match:
                    self.groups[('export_row', observation.evidence_id, match.group(2))].add(position)
            if observation.source_type == 'pdf':
                self.groups[('document', observation.evidence_id)].add(position)
            direct = direct_identifiers(observation.raw_fields)
            for field, key in direct:
                self.postings.setdefault((field, key), {}).setdefault(position, set()).add('direct')
            for original, lookup in observation.identifiers:
                field = 'email' if '@' in original else ('user_id' if USER.fullmatch(original) else
                         'phone' if original.startswith('+') else 'email_hash')
                key = norm(field, original)
                self.postings.setdefault((field, key), {}).setdefault(position, set()).add('context')

    def find(self, resolution: Resolution) -> list[Hit]:
        if resolution.status != 'resolved': return []
        keys = {(v.field, v.normalized) for v in resolution.history if v.normalized}
        keys.add(('user_id', resolution.user_id))
        selected = {}
        for key in keys:
            for position, strengths in self.postings.get(key, {}).items():
                entry = selected.setdefault(position, {'matched': set(), 'strength': set()})
                entry['matched'].add(key)
                entry['strength'].update(strengths)
        # Correlation is a candidate link, never direct identity proof. A trace
        # ID, export row position, or document is the visible join context.
        for group in self.groups.values():
            anchors = [position for position in group if position in selected]
            if not anchors: continue
            matched = set().union(*(selected[p]['matched'] for p in anchors))
            for position in group:
                entry = selected.setdefault(position, {'matched': set(), 'strength': set()})
                entry['matched'].update(matched)
                if position not in anchors: entry['strength'].add('correlated')
        output = []
        cutoff = parse_time(resolution.audit_at)
        for position in sorted(selected):
            observation = self.observations[position]
            if parse_time(observation.captured_at) > cutoff: continue
            entry = selected[position]
            strength = ('direct' if 'direct' in entry['strength'] else
                        'context' if 'context' in entry['strength'] else 'correlated')
            identities_on_record = {value for field, value in direct_identifiers(observation.raw_fields)
                                    if field in ('email', 'user_id')}
            if len(identities_on_record) > 1:
                strength = 'mixed_context'
            output.append(Hit(observation, tuple(sorted(entry['matched'])), strength))
        return output
