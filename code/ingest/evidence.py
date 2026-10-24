"""M1 evidence normalization; all source text is inert data."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shlex
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PARSER_VERSION = 'm1-v1'
EMAIL = re.compile(r'(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])')
USER = re.compile(r'\buser_\d+\b', re.I)
PHONE = re.compile(r'\+\d[\d ()-]{6,}\d')
TIME = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$')
TABLE_SYSTEM = {'customer_profiles': 'account_service', 'customer_search_documents': 'search_service',
                'customer_analytics_profiles': 'analytics_platform', 'support_records': 'support_platform',
                'customer_exports': 'export_service', 'connector_subscriptions': 'integration_service',
                'backup_restore_entries': 'backup_service', 'security_audit_records': 'security_service'}


class ExtractionError(ValueError):
    pass


def parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise ExtractionError(f'invalid timezone-aware timestamp: {value!r}')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def normalized(value: str) -> str:
    if '@' in value:
        return value.casefold()
    if value.startswith('+') and any(c.isdigit() for c in value):
        return '+' + ''.join(c for c in value if c.isdigit())
    return value


def identifiers(raw: Any) -> tuple[tuple[str, str], ...]:
    found = set()
    def walk(value, key=''):
        if isinstance(value, dict):
            for k, v in value.items(): walk(v, k)
        elif isinstance(value, list):
            for v in value: walk(v, key)
        elif isinstance(value, str):
            for item in EMAIL.findall(value) + USER.findall(value): found.add((item, normalized(item)))
            for item in PHONE.findall(value): found.add((item, normalized(item)))
            if 'phone' in key.lower() and any(c.isdigit() for c in value):
                found.add((value, normalized(value)))
            if 'hash' in key.lower() and value: found.add((value, value))
    walk(raw)
    return tuple(sorted(found))


@dataclass(frozen=True)
class Observation:
    evidence_id: str
    source_path: str
    locator: str
    captured_at: str
    system_id: str | None
    resource_id: str | None
    data_category: str | None
    state: str | None
    identifiers: tuple[tuple[str, str], ...]
    raw_fields: dict[str, Any]
    source_type: str
    topology: str | None = None
    record_time: str | None = None
    event_time: str | None = None
    source_origin: str | None = None


def make(meta, locator, raw, kind, *, system=None, category=None, topology=None, record_time=None, event_time=None):
    for time in (record_time, event_time):
        if time is not None: parse_time(time)
    return Observation(meta['file_id'], meta['file_path'], locator, meta['captured_at'],
                       system or raw.get('system_id') or raw.get('service') or raw.get('data_store'),
                       raw.get('resource_id'), category or raw.get('data_category') or raw.get('collection'),
                       next((str(raw[k]) for k in ('state', 'status', 'account_status') if raw.get(k) is not None), None),
                       identifiers(raw), raw, kind, topology, record_time, event_time, meta.get('origin'))


def topology(path: Path) -> str:
    name = path.name.lower()
    for token in ('failover', 'reporting', 'regional', 'replica'):
        if token in name: return token
    return 'primary'


def table_topology(table: str, path: Path) -> str:
    name = table.lower()
    if 'replica_' in name and any(region in name for region in ('ap_', 'eu_', 'us_', 'sa_', 'af_', 'me_', 'ca_')):
        return 'regional'
    for token in ('failover', 'reporting', 'regional', 'replica', 'primary'):
        if token in name: return token
    return topology(path)


def parse_sql(path, meta):
    script = path.read_text(encoding='utf-8')
    with sqlite3.connect(':memory:') as db:
        def guard(action, a, b, database, trigger):
            if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_CREATE_VTABLE):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and a.lower() != 'foreign_keys':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        db.set_authorizer(guard)
        db.executescript(script)
        names = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        observations = []
        counts = {}
        for table in names:
            quoted = '"' + table.replace('"', '""') + '"'
            cursor = db.execute('SELECT * FROM ' + quoted + ' ORDER BY rowid')
            cols = [c[0] for c in cursor.description]
            records = cursor.fetchall(); counts[table] = len(records)
            for number, values in enumerate(records, 1):
                raw = dict(zip(cols, values))
                if isinstance(raw.get('record_json'), str):
                    raw['parsed_record'] = json.loads(raw['record_json'])
                when = raw.get('updated_at')
                observations.append(make(meta, f'{table}[{number}]', raw, 'sql',
                                         system=raw.get('origin_system') or TABLE_SYSTEM.get(table),
                                         category=raw.get('collection_name') or table,
                                         topology=table_topology(table, path), record_time=when))
    # INSERT counts are checked against materialized records for these snapshots.
    return observations, counts


def parse_json(path, meta):
    value = json.loads(path.read_text(encoding='utf-8'))
    out = []
    def walk(node, locator='$', inherited=None):
        inherited = dict(inherited or {})
        if isinstance(node, dict):
            for k in ('system_id', 'data_store', 'collection', 'captured_at', 'observed_at'):
                if isinstance(node.get(k), str): inherited[k] = node[k]
            if 'resource_id' in node:
                when = next((node[k] for k in ('observed_at', 'updated_at', 'recorded_at')
                             if isinstance(node.get(k), str) and TIME.fullmatch(node[k])), None)
                raw = dict(node)
                out.append(make(meta, locator, raw, 'json',
                                system=inherited.get('system_id') or inherited.get('data_store'),
                                category=inherited.get('collection'), record_time=when))
            for key, child in node.items():
                if isinstance(child, (dict, list)):
                    child_context = dict(inherited)
                    if locator.endswith('service_exports') and isinstance(child, dict): child_context['system_id'] = key
                    walk(child, locator + '.' + key, child_context)
        elif isinstance(node, list):
            for i, child in enumerate(node): walk(child, f'{locator}[{i}]', inherited)
    walk(value)
    if not out:
        out.append(make(meta, '$', {'document': value}, 'json'))
    return out


def parse_lines(path, meta, kind, text=None):
    if text is None: text = path.read_text(encoding='utf-8')
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip(): continue
        raw = {'text': line}
        parts = [p.strip() for p in line.lstrip('- ').split('|')]
        if len(parts) >= 5 and TIME.fullmatch(parts[0]):
            raw.update(zip(('event_time', 'system_id', 'resource_id', 'data_category', 'state'), parts[:5]))
            if len(parts) > 5: raw['identifiers_text'] = '|'.join(parts[5:])
        else:
            try: tokens = shlex.split(line)
            except ValueError: tokens = line.split()
            for token in tokens:
                if '=' in token:
                    key, value = token.split('=', 1)
                    if key and re.fullmatch(r'[A-Za-z_][\w-]*', key): raw[key] = value
            first = line.split(maxsplit=1)[0]
            if TIME.fullmatch(first): raw['event_time'] = first
        when = raw.get('event_time')
        if when and not TIME.fullmatch(when): when = None
        out.append(make(meta, f'line:{number}', raw, kind, event_time=when))
    return out


def parse_pdf(path, meta):
    try:
        run = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True,
                             text=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExtractionError(f'{meta["file_id"]}: pdftotext failed: {exc}') from exc
    if not run.stdout.strip(): return [], 'needs_multimodal'
    return parse_lines(path, meta, 'pdf', run.stdout), 'parsed'


def source_digest(path):
    parser_hash = hashlib.sha256(Path(__file__).read_bytes()).digest()
    return hashlib.sha256(PARSER_VERSION.encode() + parser_hash + path.read_bytes()).hexdigest()


def embedded_capture(path: Path):
    if path.suffix == '.json':
        value = json.loads(path.read_text(encoding='utf-8'))
        return value.get('exported_at') or value.get('captured_at')
    if path.suffix == '.sql':
        text = path.read_text(encoding='utf-8')
        found = re.search(r'(?m)^-- (?:Captured at|snapshot_completed_at)[:=]\s*(\S+)', text)
        return found.group(1) if found else None
    return None


def ingest(dataset: Path, cache: Path | None = None):
    dataset = Path(dataset).resolve()
    manifest = list(csv.DictReader((dataset / 'evidence_files.csv').open(encoding='utf-8', newline='')))
    if len({m['file_id'] for m in manifest}) != len(manifest): raise ExtractionError('duplicate file_id')
    output = []; coverage = []; discrepancies = []
    for meta in manifest:
        parse_time(meta['captured_at'])
        path = (dataset / meta['file_path']).resolve()
        if not path.is_relative_to(dataset / 'evidence') or not path.is_file():
            raise ExtractionError(f'unsafe or missing evidence path: {meta["file_id"]}')
        suffix = path.suffix.lower(); counts = {}
        if suffix == '.png': obs = []; status = 'needs_multimodal'
        else:
            key = source_digest(path) + '-' + hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()
            cached = cache / (key + '.json') if cache else None
            if cached and cached.exists():
                payload = json.loads(cached.read_text())
                obs = [Observation(**{**r, 'identifiers': tuple(tuple(pair) for pair in r['identifiers'])})
                       for r in payload['observations']]
                counts = payload['tables']; status = payload['status']
            else:
                if suffix == '.sql': obs, counts = parse_sql(path, meta); status = 'parsed'
                elif suffix == '.json': obs = parse_json(path, meta); status = 'parsed'
                elif suffix in ('.log', '.txt'): obs = parse_lines(path, meta, suffix[1:]); status = 'parsed'
                elif suffix == '.pdf': obs, status = parse_pdf(path, meta)
                else: raise ExtractionError(f'{meta["file_id"]}: unsupported format {suffix}')
                if cached:
                    cache.mkdir(parents=True, exist_ok=True)
                    temp = cached.with_suffix('.tmp')
                    temp.write_text(json.dumps({'observations': [asdict(o) for o in obs], 'tables': counts,
                                                'status': status}, sort_keys=True, ensure_ascii=False))
                    temp.replace(cached)
        output.extend(obs)
        internal_capture = embedded_capture(path) if suffix in ('.json', '.sql') else None
        if internal_capture is not None and internal_capture != meta['captured_at']:
            discrepancies.append({'file_id': meta['file_id'], 'locator': '$',
                                  'reason': 'file_capture_disagrees_with_manifest',
                                  'internal_capture': internal_capture})
        coverage.append({'file_id': meta['file_id'], 'source_path': meta['file_path'], 'format': suffix,
                         'status': status, 'observations': len(obs), 'tables': counts,
                         'topology': topology(path) if suffix == '.sql' else None,
                         'origin': meta['origin'], 'embedded_capture': internal_capture})
        for o in obs:
            if o.record_time and o.record_time > o.captured_at:
                discrepancies.append({'file_id': o.evidence_id, 'locator': o.locator,
                                      'reason': 'record_time_after_manifest_capture'})
    for filename, key, when in [('system_activity.csv', 'activity_id', 'event_time'),
                                ('user_audit_log.csv', 'audit_id', 'event_time')]:
        with (dataset / filename).open(encoding='utf-8', newline='') as stream:
            for number, raw in enumerate(csv.DictReader(stream), 2):
                stamp = raw[when]; parse_time(stamp)
                meta = {'file_id': raw[key], 'file_path': filename, 'captured_at': stamp}
                output.append(make(meta, f'row:{number}', raw, 'activity' if key == 'activity_id' else 'audit',
                                   event_time=stamp))
    return output, coverage, discrepancies


def canonical_bytes(observations):
    return ('\n'.join(json.dumps(asdict(o), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
                      for o in observations) + '\n').encode()
