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
    def __init__(self, observations: list[Observation], anomalies=frozenset()):
        self.observations = observations
        self.anomalies = frozenset(anomalies)
        self.postings = {}
        self.trace_groups = defaultdict(set)
        for position, observation in enumerate(observations):
            raw = observation.raw_fields
            if observation.source_type == 'log' and raw.get('trace_id'):
                self.trace_groups[(observation.evidence_id, raw['trace_id'])].add(position)
            direct = direct_identifiers(observation.raw_fields)
            for field, key in direct:
                self.postings.setdefault((field, key), {}).setdefault(position, set()).add('direct')
            for original, lookup in observation.identifiers:
                field = 'email' if '@' in original else ('user_id' if USER.fullmatch(original) else
                         'phone' if original.startswith('+') else 'email_hash')
                key = norm(field, original)
                self.postings.setdefault((field, key), {}).setdefault(position, set()).add('context')

    def _anchor_admissible(self, position: int, cutoff) -> bool:
        o = self.observations[position]
        if parse_time(o.captured_at) > cutoff or (o.evidence_id, o.locator) in self.anomalies:
            return False
        for stamp in (o.record_time, o.event_time):
            if stamp and (parse_time(stamp) > cutoff or parse_time(stamp) > parse_time(o.captured_at)):
                return False
        return True

    def find(self, resolution: Resolution) -> list[Hit]:
        return self._find(resolution)[0]

    def excluded_visual(self, resolution: Resolution) -> list[Hit]:
        """Screenshot rows that match the subject but are not evidence at the
        cutoff (M8 quarantine, or captured/recorded after it). Kept for
        diagnostics only; they never link a resource to the subject."""
        return self._find(resolution)[1]

    def _find(self, resolution: Resolution) -> tuple[list[Hit], list[Hit]]:
        if resolution.status != 'resolved': return [], []
        keys = {(v.field, v.normalized) for v in resolution.history if v.normalized}
        keys.add(('user_id', resolution.user_id))
        selected = {}
        for key in keys:
            for position, strengths in self.postings.get(key, {}).items():
                entry = selected.setdefault(position, {'matched': set(), 'strength': set()})
                entry['matched'].add(key)
                entry['strength'].update(strengths)
        # Only an explicit shared trace ID is a cross-line join. Distinct
        # customer identifiers within one trace make that group ambiguous.
        # Only lines that are evidence at the cutoff may anchor or contest it.
        cutoff = parse_time(resolution.audit_at)
        for group in self.trace_groups.values():
            group = {p for p in group if self._anchor_admissible(p, cutoff)}
            identities = set()
            for position in group:
                identities.update((f, v) for f, v in direct_identifiers(
                    self.observations[position].raw_fields) if f in ('email', 'user_id'))
            if len(identities) > 1: continue
            anchors = [position for position in group if position in selected]
            if not anchors: continue
            matched = set().union(*(selected[p]['matched'] for p in anchors))
            for position in group:
                entry = selected.setdefault(position, {'matched': set(), 'strength': set()})
                entry['matched'].update(matched)
                if position not in anchors: entry['strength'].add('correlated')
        output, excluded = [], []
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
            hit = Hit(observation, tuple(sorted(entry['matched'])), strength)
            # M8: an inadmissible screenshot row cannot establish that the subject
            # has this resource; another admissible observation must do that.
            if observation.source_type == 'image' and not self._anchor_admissible(position, cutoff):
                excluded.append(hit)
                continue
            output.append(hit)
        return output, excluded
