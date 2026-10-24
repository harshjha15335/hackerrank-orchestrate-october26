"""Turn validated screenshot extractions into M1 ``Observation`` rows.

Only a record the screen labels with a resource ID, in customer or process
scope, becomes an observation. Its raw fields are that record's visible fields
and nothing from the rest of the screen, so query history, timelines or other
rows never lend it an identity. The adapter assigns no subject, state or
policy: M2 attributes it, M4/M6 read its state, M5 applies policy and the M7
guard re-checks any citation, exactly as for other evidence.

Temporal handling follows M1: the manifest capture time is the capture time
and is never changed. Each visible time has a role (schema.py): a record's own
time, an expiry, the time its result set was generated, or other page metadata.
A record whose own stated time is after that capture is quarantined. So is
every record of a result set (a query result, a list rendered together) whose
generation time, or any row's own time, shows that the set as displayed was
produced after the capture: the screen cannot show that set's state at
capture. Expiry and unrelated page times never quarantine; they are reported.
Times without a stated date, year or zone stay text and decide nothing (see
times.py).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ingest.evidence import Observation, identifiers, parse_time
from state.engine import KNOWN_SYSTEMS

from .extract import Extractor, FixtureProvider
from .times import page_year, resolve

CATEGORY_MAP = Path(__file__).resolve().parents[1] / 'policy' / 'category_map.json'
EMITTED = ('customer_record', 'process_record')
RECORD_AFTER_CAPTURE = 'record_time_after_manifest_capture'
SET_AFTER_CAPTURE = 'result_set_rendered_after_manifest_capture'
QUARANTINE_REASONS = (RECORD_AFTER_CAPTURE, SET_AFTER_CAPTURE)


def prefix_systems(path: Path = CATEGORY_MAP) -> dict[str, str]:
    """resource prefix -> owning system, from M5's declarative prefix map."""
    mapping = json.loads(path.read_text(encoding='utf-8'))['resource_prefixes']
    return {prefix: system for system, prefixes in mapping.items() for prefix in prefixes}


def owning_system(resource_id: str, origin: str | None, prefixes: dict[str, str]) -> tuple[str | None, str]:
    matches = sorted((p for p in prefixes if resource_id.startswith(p)), key=len)
    by_prefix = prefixes[matches[-1]] if matches else None
    by_origin = origin if origin in KNOWN_SYSTEMS else None
    if by_prefix and by_origin and by_prefix != by_origin:
        return None, f'resource prefix says {by_prefix}, manifest origin says {by_origin}'
    if by_prefix: return by_prefix, 'resource prefix'
    if by_origin: return by_origin, 'manifest origin'
    return None, 'no prefix or known-system origin'


@dataclass
class VisualEvidence:
    observations: list
    discrepancies: list
    extractions: list
    records: list        # per-record report rows (emitted or not, with reasons)
    unresolved_times: list
    counters: dict
    ledger: list


def adapt(extraction, prefixes) -> tuple[list, list, list, list]:
    meta, doc = extraction.meta, extraction.document
    captured = parse_time(meta['captured_at'])
    year = page_year(doc)
    observations, discrepancies, rows, unresolved = [], [], [], []

    def emitted(r):
        return r['scope'] in EMITTED and r['resource_id'] is not None

    def times_of(items, where):
        out = []
        for t in items:
            iso, how = resolve(t['text'], t.get('tz_label'), year)
            out.append(dict(t, iso=iso, how=how))
            if iso is None:
                unresolved.append({'file_id': meta['file_id'], 'where': where, 'text': t['text'], 'reason': how})
            elif parse_time(iso) > captured and t['role'] in ('record', 'page') and not (
                    t['role'] == 'record' and where.startswith('image:')):
                # Reported only: a page time or the time of a row that is not emitted.
                discrepancies.append({'file_id': meta['file_id'], 'locator': where,
                                      'reason': 'screen_time_after_manifest_capture',
                                      'visible_time': t['text'], 'resolved': iso})
        return out

    generated = defaultdict(list)     # result set -> resolved generation times
    for t in times_of(doc['screen']['times'], 'screen'):
        if t['role'] == 'generated' and t['iso']: generated[t['result_set']].append((t['iso'], t['text'], 'screen'))
    for i, c in enumerate(doc['context']): times_of(c['times'], f'context[{i}]')
    stamps, members = {}, defaultdict(list)
    for r in doc['records']:
        locator = f'image:{r["record_key"]}'
        stamps[r['record_key']] = times_of(r['times'], locator if emitted(r) else f'screen:{r["record_key"]}')
        members[r.get('result_set', r['record_key'])].append(r)
        for t in stamps[r['record_key']]:
            if t['role'] == 'generated' and t['iso']: generated[t['result_set']].append((t['iso'], t['text'], locator))
    # Lower bound on when each result set was rendered: its generation times and
    # every member row's own resolved times. Expiries and page times are not in it.
    bound = {}
    for name, rs in members.items():
        points = list(generated[name]) + [(t['iso'], t['text'], f'image:{r["record_key"]}')
                                          for r in rs for t in stamps[r['record_key']]
                                          if t['role'] == 'record' and t['iso']]
        if points: bound[name] = max(points, key=lambda x: parse_time(x[0]))

    for r in doc['records']:
        locator = f'image:{r["record_key"]}'
        own = stamps[r['record_key']]
        row = {'file_id': meta['file_id'], 'locator': locator, 'resource_id': r['resource_id'], 'scope': r['scope'],
               'emitted': False, 'system_id': None, 'reason': None}
        rows.append(row)
        if r['scope'] not in EMITTED:
            row['reason'] = f'scope {r["scope"]} is not a record of its own'
            continue
        if r['resource_id'] is None:
            row['reason'] = 'no resource ID is visible for this record'
            continue
        system, basis = owning_system(r['resource_id'], meta.get('origin'), prefixes)
        row['system_id'] = system
        if system is None:
            row['reason'] = basis
            continue
        record_times = [s['iso'] for s in own if s['role'] == 'record' and s['iso']]
        for t in own:
            if t['role'] == 'record' and t['iso'] and parse_time(t['iso']) > captured:
                discrepancies.append({'file_id': meta['file_id'], 'locator': locator, 'reason': RECORD_AFTER_CAPTURE,
                                      'visible_time': t['text'], 'resolved': t['iso']})
        result_set = r.get('result_set', r['record_key'])
        event_time = None
        if result_set in bound and parse_time(bound[result_set][0]) > captured:
            iso, text, source = bound[result_set]
            discrepancies.append({'file_id': meta['file_id'], 'locator': locator, 'reason': SET_AFTER_CAPTURE,
                                  'result_set': result_set, 'visible_time': text, 'resolved': iso,
                                  'established_by': source})
            event_time = iso      # the set as shown was rendered no earlier than this
        elif generated[result_set]:
            event_time = max(generated[result_set], key=lambda x: parse_time(x[0]))[0]
        expiries = [s['iso'] for s in own if s['role'] == 'expiry' and s['iso']]
        fields = {f['name']: f['value'] for f in r['fields']}
        raw = dict(fields, resource_id=r['resource_id'])
        if expiries: raw['expires_at'] = min(expiries)
        raw['visual'] = {'record_key': r['record_key'], 'panel': r['panel'],
                         'method': doc['provenance']['method']}
        observations.append(Observation(
            meta['file_id'], meta['file_path'], locator, meta['captured_at'], system, r['resource_id'],
            None, None, identifiers(fields), raw, 'image', None,
            max(record_times, key=parse_time) if record_times else None, event_time, meta.get('origin')))
        row.update(emitted=True, reason=f'system from {basis}')
    return observations, discrepancies, rows, unresolved


def load(dataset: Path, cache: Path | None = None, provider=None) -> VisualEvidence:
    extractor = Extractor(provider or FixtureProvider(), cache)
    extractions = extractor.run(dataset)
    prefixes = prefix_systems()
    observations, discrepancies, records, unresolved = [], [], [], []
    for e in extractions:
        if e.document is None:
            records.append({'file_id': e.meta['file_id'], 'locator': None, 'resource_id': None, 'scope': None,
                            'emitted': False, 'system_id': None, 'reason': f'invalid extraction: {e.error}'})
            continue
        o, d, r, u = adapt(e, prefixes)
        observations += o; discrepancies += d; records += r; unresolved += u
    return VisualEvidence(observations, discrepancies, extractions, records, unresolved,
                          dict(extractor.counters), extractor.ledger)
