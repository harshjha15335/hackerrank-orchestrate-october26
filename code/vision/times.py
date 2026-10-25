"""Resolve timestamps shown on a screen into UTC, or leave them unresolved.

A visible time becomes an instant only when the screen states its date, time
and time zone. A missing year is taken from the screen only when every fully
dated time on it shares one year; a missing zone only from a column label that
names it (for example "Time (UTC)"). Anything else stays text: it can neither
quarantine a record nor make one admissible.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ingest.evidence import TIME, parse_time

MONTHS = {m: i for i, m in enumerate(('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                                      'Sep', 'Oct', 'Nov', 'Dec'), 1)}
ZONES = {'UTC': 0, 'GMT': 0, 'JST': 9}
DATED = re.compile(r'(\d{1,2}) ([A-Z][a-z]{2})(?: (\d{4}))? (\d{2}):(\d{2})(?::(\d{2}))?(?: ([A-Z]{3}))?\Z')
LABEL_ZONE = re.compile(r'\(([A-Z]{3})\)')


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def stated_year(text: str) -> int | None:
    """Year of a fully stated time (date, year, time and zone), else None."""
    if TIME.fullmatch(text): return parse_time(text).year
    found = DATED.fullmatch(text)
    if found and found.group(3) and found.group(7) in ZONES and found.group(2) in MONTHS:
        return int(found.group(3))
    return None


def resolve(text: str, tz_label: str | None = None, page_year: int | None = None):
    """Return (iso_utc | None, how) for one visible time."""
    if TIME.fullmatch(text):
        return _iso(parse_time(text)), 'iso timestamp'
    found = DATED.fullmatch(text)
    if not found or found.group(2) not in MONTHS:
        return None, 'not a dated time'
    day, month, year, hh, mm, ss, zone = found.groups()
    how = []
    if zone is None and tz_label:
        label = LABEL_ZONE.search(tz_label)
        zone = label.group(1) if label else None
        if zone: how.append(f'zone from label {tz_label!r}')
    if zone not in ZONES:
        return None, 'no time zone shown'
    if year is None:
        if page_year is None:
            return None, 'no year shown and the screen has no single stated year'
        year = page_year
        how.append(f'year {page_year} from the screen')
    try:
        moment = datetime(int(year), MONTHS[month], int(day), int(hh), int(mm), int(ss or 0),
                          tzinfo=timezone(timedelta(hours=ZONES[zone])))
    except ValueError:
        return None, 'not a calendar time'
    return _iso(moment), '; '.join(how) or 'stated'


def page_year(doc: dict) -> int | None:
    years = set()
    entries = list(doc['screen']['times'])
    for r in doc['records']: entries.extend(r['times'])
    for c in doc['context']: entries.extend(c['times'])
    for t in entries:
        year = stated_year(t['text'])
        if year: years.add(year)
    return years.pop() if len(years) == 1 else None
