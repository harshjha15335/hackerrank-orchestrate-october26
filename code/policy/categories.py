"""Map observed records to deletion_rules.csv categories from declarative signals."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from state.engine import field_values

CONFIG = Path(__file__).with_name('category_map.json')
RANKS = ('explicit_label', 'collection', 'record_fields', 'document_text', 'readback_event', 'scan_event',
         'resource_prefix')


def load_map(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass(frozen=True)
class CategoryResult:
    category: str | None
    status: str          # MAPPED, PROCESS, UNMAPPED, AMBIGUOUS
    basis: str
    candidates: tuple[tuple[str, str], ...]


def _signals(o, system_id, resource_id, known, cmap):
    out = []
    raw = o.raw_fields
    fields = field_values(raw)
    labels = {o.data_category, raw.get('collection_name'), raw.get('record_type'), raw.get('data_category')}
    for label in sorted(filter(None, labels)):
        if label in known: out.append(('explicit_label', label))
        elif label in cmap['collections']: out.append(('collection', cmap['collections'][label]))
    for signal in cmap['field_signals']:
        if signal.get('systems') and system_id not in signal['systems']: continue
        if any(name in fields for name in signal['fields']):
            out.append(('record_fields', signal['category']))
    if raw.get('event') in cmap['event_signals']:
        out.append(('readback_event', cmap['event_signals'][raw['event']]))
    if o.source_type == 'pdf' and o.locator == f'document:{resource_id}' and o.source_origin == system_id:
        text = raw.get('text') or ''
        for signal in cmap.get('document_signals', ()):
            if system_id in signal['systems'] and all(re.search(p, text) for p in signal['patterns']):
                out.append(('document_text', signal['category']))
    scan = cmap.get('scan_event_signals', {}).get(raw.get('event'))
    # Only the owning service's own scan of this resource names its content kind.
    if (scan and o.source_type == 'log' and system_id in scan['systems'] and raw.get('service') == system_id
            and raw.get('resource_id') == resource_id):
        out.append(('scan_event', scan['category']))
    return out


def classify(observations, system_id, resource_id, policy_categories, cmap) -> CategoryResult:
    """Highest-ranked signal wins; disagreement at that rank is not guessed."""
    known = set(policy_categories) | set(cmap['process_categories'])
    signals = set()
    for o in observations:
        signals.update(_signals(o, system_id, resource_id, known, cmap))
    # The system and resource ID come from the M4 assertion itself, not a record.
    for prefix, category in cmap['resource_prefixes'].get(system_id or '', {}).items():
        if resource_id and resource_id.startswith(prefix):
            signals.add(('resource_prefix', category))
    for rank in RANKS:
        found = sorted({c for r, c in signals if r == rank})
        if not found: continue
        candidates = tuple(sorted(signals))
        if len(found) > 1:
            return CategoryResult(None, 'AMBIGUOUS', rank, candidates)
        category = found[0]
        if category in cmap['process_categories']:
            return CategoryResult(category, 'PROCESS', rank, candidates)
        if category not in policy_categories:
            return CategoryResult(category, 'UNMAPPED', rank, candidates)
        return CategoryResult(category, 'MAPPED', rank, candidates)
    return CategoryResult(None, 'UNMAPPED', 'no_signal', tuple(sorted(signals)))
