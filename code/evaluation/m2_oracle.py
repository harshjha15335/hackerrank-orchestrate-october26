"""Independent, source-grounded oracle for cited dev pairs.

This module examines parsed source fields and explicit trace relationships.
It never calls EvidenceIndex, reads its postings, or classifies from hits.
"""
import re

from ingest.evidence import parse_time

EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
USER = re.compile(r'\buser_\d+\b', re.I)
PHONE = re.compile(r'\+\d[\d ()-]{6,}\d')
HASH = re.compile(r'[0-9a-fA-F]{64}\Z')
IDENTITY_FIELDS = {'user_id', 'subject_reference', 'customer_reference', 'email',
                   'email_hash', 'phone', 'owner_email', 'owner_phone',
                   'requester_email', 'requester_phone', 'customer_email',
                   'lookup_key', 'correlation_key', 'subject_key', 'matched_value',
                   'identifiers_text', 'old_value', 'new_value'}


def source_tokens(value, field=''):
    """Extract only whole identifiers from explicit source fields."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items(): found.update(source_tokens(item, key))
    elif isinstance(value, list):
        for item in value: found.update(source_tokens(item, field))
    elif isinstance(value, str) and (field in IDENTITY_FIELDS or
                                      field.endswith(('_email', '_phone', '_hash'))):
        found.update(('email', item.casefold()) for item in EMAIL.findall(value))
        found.update(('user_id', item) for item in USER.findall(value))
        found.update(('phone', ''.join(ch for ch in item if ch.isdigit()))
                     for item in PHONE.findall(value))
        if 'hash' in field and value: found.add(('email_hash', value))
        if field == 'correlation_key' and HASH.fullmatch(value): found.add(('email_hash', value))
    return found


def identity_keys(resolution):
    keys = {(value.field, value.normalized) for value in resolution.history if value.normalized}
    keys.add(('user_id', resolution.user_id))
    return keys


def supported_pair(resolution, evidence_id, resource_id, observations):
    """Return an independent source locator/reason, or None if unsupported."""
    if resolution.status != 'resolved': return None
    cutoff = parse_time(resolution.audit_at)
    source = [o for o in observations if o.evidence_id == evidence_id and
              parse_time(o.captured_at) <= cutoff]
    targets = [o for o in source if o.resource_id == resource_id]
    keys = identity_keys(resolution)
    for target in targets:
        if source_tokens(target.raw_fields) & keys:
            return (target.locator, 'explicit_identifier')
        if target.source_type == 'pdf' and target.locator == f'document:{resource_id}':
            text = target.raw_fields.get('text', '')
            emails = {item.casefold() for item in EMAIL.findall(text)}
            users = set(USER.findall(text))
            if len(emails) == 1 and len(users) <= 1 and any(('email', x) in keys for x in emails):
                return (target.locator, 'single_subject_document')
        if target.source_type == 'log' and target.raw_fields.get('trace_id'):
            trace = target.raw_fields['trace_id']
            group = [o for o in source if o.source_type == 'log' and
                     o.raw_fields.get('trace_id') == trace]
            identities = set().union(*(source_tokens(o.raw_fields) for o in group))
            primary = {(f, v) for f, v in identities if f in ('email', 'user_id')}
            if len(primary) <= 1 and identities & keys:
                return (target.locator, f'explicit_trace:{trace}')
    return None
