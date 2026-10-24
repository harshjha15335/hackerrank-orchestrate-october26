"""M8 structured-output schema for one screenshot extraction (strict, no coercion).

The same schema binds a manual fixture and a model response. Every key is
required and nothing else is allowed, so a response that adds instructions,
verdicts or invented keys is rejected rather than trusted. Values are the text
shown on screen; nothing here interprets them.
"""
from __future__ import annotations

import re

SCHEMA_VERSION = 'm8-visual-v1'
METHODS = ('manual_fixture', 'model')
PANELS = re.compile(r'[a-z_]+(?:\+[a-z_]+)*\Z')
NAME = re.compile(r'[a-z_][a-z0-9_]*\Z')
RESOURCE = re.compile(r'[a-z]+(?:_[a-z]+)*_\d+\Z')
# customer_record / process_record become observations when a resource ID is
# visible; the other scopes are kept for provenance only.
SCOPES = ('customer_record', 'process_record', 'reference_only', 'non_customer',
          'linked_context', 'unattributed_object')
ROLES = ('record', 'expiry', 'page')
TOP = {'schema_version', 'file_id', 'file_path', 'image_sha256', 'provenance', 'screen',
       'records', 'context', 'not_visible'}
PROVENANCE = {'manual_fixture': {'method', 'model_call', 'transcriber', 'transcribed_on', 'origin_note'},
              'model': {'method', 'model_call', 'provider', 'model', 'prompt_version'}}


class SchemaError(ValueError):
    pass


def _keys(value, required, optional=(), where=''):
    if not isinstance(value, dict):
        raise SchemaError(f'{where}: expected an object')
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing: raise SchemaError(f'{where}: missing {sorted(missing)}')
    if extra: raise SchemaError(f'{where}: unexpected {sorted(extra)}')


def _text(value, where, nullable=False):
    if value is None and nullable: return
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f'{where}: expected non-empty text')


def _times(items, where):
    if not isinstance(items, list): raise SchemaError(f'{where}: expected a list')
    for i, t in enumerate(items):
        w = f'{where}[{i}]'
        _keys(t, ('label', 'text', 'role'), ('tz_label',), w)
        _text(t['label'], w + '.label'); _text(t['text'], w + '.text')
        if t['role'] not in ROLES: raise SchemaError(f'{w}.role: {t["role"]!r}')
        if 'tz_label' in t: _text(t['tz_label'], w + '.tz_label')


def validate(doc: dict, *, file_id: str, file_path: str, image_sha256: str) -> dict:
    """Raise SchemaError unless ``doc`` is a complete extraction of this exact image."""
    _keys(doc, TOP, (), '$')
    if doc['schema_version'] != SCHEMA_VERSION:
        raise SchemaError(f'$.schema_version: {doc["schema_version"]!r}')
    if (doc['file_id'], doc['file_path']) != (file_id, file_path):
        raise SchemaError('$: extraction names another manifest entry')
    if doc['image_sha256'] != image_sha256:
        raise SchemaError('$.image_sha256: extraction was made from different image bytes')
    prov = doc['provenance']
    if not isinstance(prov, dict) or prov.get('method') not in METHODS:
        raise SchemaError('$.provenance.method must be manual_fixture or model')
    _keys(prov, PROVENANCE[prov['method']], (), '$.provenance')
    if prov['model_call'] is not (prov['method'] == 'model'):
        raise SchemaError('$.provenance.model_call contradicts the method')
    screen = doc['screen']
    _keys(screen, ('application', 'title', 'subtitle', 'times'), (), '$.screen')
    for k in ('application', 'title', 'subtitle'): _text(screen[k], f'$.screen.{k}')
    _times(screen['times'], '$.screen.times')
    if not isinstance(doc['records'], list) or not doc['records']:
        raise SchemaError('$.records: expected a non-empty list')
    keys = set()
    for i, r in enumerate(doc['records']):
        w = f'$.records[{i}]'
        _keys(r, ('record_key', 'panel', 'scope', 'resource_id', 'fields', 'times'), ('note',), w)
        _text(r['record_key'], w + '.record_key')
        if r['record_key'] in keys: raise SchemaError(f'{w}.record_key: duplicate')
        keys.add(r['record_key'])
        if not isinstance(r['panel'], str) or not PANELS.fullmatch(r['panel']):
            raise SchemaError(f'{w}.panel: {r["panel"]!r}')
        if r['scope'] not in SCOPES: raise SchemaError(f'{w}.scope: {r["scope"]!r}')
        if r['resource_id'] is not None and (not isinstance(r['resource_id'], str)
                                             or not RESOURCE.fullmatch(r['resource_id'])):
            raise SchemaError(f'{w}.resource_id: {r["resource_id"]!r}')
        if 'note' in r: _text(r['note'], w + '.note')
        if not isinstance(r['fields'], list) or not r['fields']:
            raise SchemaError(f'{w}.fields: expected a non-empty list')
        names = set()
        for j, f in enumerate(r['fields']):
            fw = f'{w}.fields[{j}]'
            _keys(f, ('label', 'name', 'value'), (), fw)
            _text(f['label'], fw + '.label')
            if not isinstance(f['name'], str) or not NAME.fullmatch(f['name']) or f['name'] == 'visual':
                raise SchemaError(f'{fw}.name: {f["name"]!r}')
            if f['name'] in names: raise SchemaError(f'{fw}.name: duplicate {f["name"]!r}')
            names.add(f['name'])
            _text(f['value'], fw + '.value', nullable=True)
        _times(r['times'], w + '.times')
    if not isinstance(doc['context'], list): raise SchemaError('$.context: expected a list')
    for i, c in enumerate(doc['context']):
        _keys(c, ('label', 'text', 'times'), (), f'$.context[{i}]')
        _text(c['label'], f'$.context[{i}].label'); _text(c['text'], f'$.context[{i}].text')
        _times(c['times'], f'$.context[{i}].times')
    if not isinstance(doc['not_visible'], list) or not all(isinstance(x, str) and x for x in doc['not_visible']):
        raise SchemaError('$.not_visible: expected a list of text')
    return doc
