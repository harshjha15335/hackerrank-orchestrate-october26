"""Read the state of a data flow or restore path from one M1 observation.

A reading says what one observation shows about a process at one moment and
how much that observation can prove. It never decides ownership or the case
state; engine.py does that. Worker results and "Policy action completed" rows
are claims: they are kept for provenance and never become a state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ingest.evidence import Observation, parse_time
from state.engine import _state_for_observation, parse_source_bool, system_for

FLOW, RESTORE = 'DATA_FLOW', 'RESTORE_PATH'
# Only an explicit system + resource prefix identifies a process resource.
PROCESS_SYSTEMS = {'integration_service': ('data_flow_', FLOW), 'backup_service': ('backup_', RESTORE)}
RISK = {FLOW: 'ACTIVE', RESTORE: 'RESTORE_ENABLED'}
SAFE = {FLOW: 'DISABLED', RESTORE: 'RESTORE_BLOCKED'}
# A favourable (safe) state needs a source read, snapshot, observed config or
# a status the owning service emitted for this resource. Inventory listings
# (another service's FOUND/ACTIVE/BLOCKED words) may show risk but never prove safety.
SAFE_PROOF = frozenset({'snapshot', 'readback', 'field_values', 'telemetry'})
RELIABILITY = {'snapshot': 4, 'readback': 3, 'field_values': 3, 'telemetry': 2,
               'visual': 1, 'inventory': 1, 'claim': 0, 'none': 0}
# M8 screenshots of a connector console: a continuous sync mode together with a
# running status shows risk. A screenshot never proves a safe state.
VISUAL_FLOW = {'mode_fields': ('sync_mode', 'mode'), 'running_modes': {'continuous', 'continuous sync'},
               'status_fields': ('status',), 'running_statuses': {'healthy', 'active', 'running'}}
# Inventory vocabularies. A backup that is merely FOUND/PRESENT says nothing
# about restore access, so it is not in the restore vocabulary.
INVENTORY_STATES = {FLOW: {'ACTIVE': 'ACTIVE', 'ENABLED': 'ACTIVE', 'DISABLED': 'DISABLED'},
                    RESTORE: {'ACTIVE': 'RESTORE_ENABLED', 'ENABLED': 'RESTORE_ENABLED',
                              'BLOCKED': 'RESTORE_BLOCKED'}}
INVENTORY_CATEGORY = {FLOW: 'DATA_FLOW', RESTORE: 'BACKUP_ARCHIVE'}
CLAIM_EVENTS = {'CHECK_DATA_FLOW', 'DISABLE_DATA_FLOW', 'BLOCK_RESTORE', 'CHECK_RESTORE_ACCESS'}


def process_kind(system_id: str | None, resource_id: str | None) -> str | None:
    if not system_id or not resource_id or system_id not in PROCESS_SYSTEMS: return None
    prefix, kind = PROCESS_SYSTEMS[system_id]
    return kind if resource_id.startswith(prefix) else None


def observation_kind(o: Observation) -> str | None:
    return process_kind(system_for(o) if o.source_type != 'activity' else o.raw_fields.get('target_system'),
                        o.resource_id)


@dataclass(frozen=True)
class Reading:
    evidence_id: str
    locator: str
    source_type: str
    captured_at: str
    observed_at: str
    state: str           # ACTIVE / DISABLED / RESTORE_ENABLED / RESTORE_BLOCKED / UNKNOWN
    evidence_class: str  # snapshot / readback / field_values / telemetry / inventory / claim / none
    basis: str
    claimed: str | None = None

    def as_dict(self):
        return asdict(self)


def observed_time(o: Observation) -> str:
    """When the state was seen to hold: a log/inventory line's own time, a JSON
    entry's observed_at, otherwise the snapshot capture time."""
    if o.event_time: return o.event_time
    if o.source_type == 'json' and o.record_time: return o.record_time
    return o.captured_at


def _claim(o: Observation, kind: str) -> Reading:
    raw = o.raw_fields
    event = raw.get('event_type')
    claimed = None
    details = str(raw.get('details', ''))
    if event == 'CHECK_DATA_FLOW' and 'remains enabled' in details: claimed = RISK[FLOW]
    elif event == 'CHECK_RESTORE_ACCESS' and 'can still be restored' in details: claimed = RISK[RESTORE]
    elif event == 'DISABLE_DATA_FLOW': claimed = SAFE[FLOW]
    elif event == 'BLOCK_RESTORE': claimed = SAFE[RESTORE]
    return Reading(o.evidence_id, o.locator, o.source_type, o.captured_at, observed_time(o), 'UNKNOWN',
                   'claim', f'{event} {raw.get("reported_result")} is a workflow claim', claimed)


def _telemetry(o: Observation, kind: str):
    """Resource-scoped status emitted by the owning service itself."""
    raw = o.raw_fields
    event = raw.get('event')
    if (o.source_type != 'log' or not o.event_time or raw.get('resource_id') != o.resource_id or
            raw.get('service') != o.system_id):
        return None
    if kind == FLOW and event in ('connector_heartbeat', 'connector_config_loaded'):
        enabled, scheduled = parse_source_bool(raw.get('enabled')), parse_source_bool(raw.get('scheduler_registered'))
        if enabled is True and scheduled is not False:
            return 'ACTIVE', f'{event} reports an enabled connector'
        if enabled is False and scheduled is not True:
            return 'DISABLED', f'{event} reports a disabled, unscheduled connector'
        return 'UNKNOWN', f'{event} flags are missing or contradictory'
    if kind == RESTORE and event == 'restore_candidate_evaluated':
        eligible, blocked = parse_source_bool(raw.get('eligible')), parse_source_bool(raw.get('deletion_block'))
        if eligible is True and blocked is False:
            return 'RESTORE_ENABLED', 'restore evaluation: eligible and no deletion block'
        if blocked is True or eligible is False:
            return 'RESTORE_BLOCKED', 'restore evaluation: ineligible or deletion block set'
        return 'UNKNOWN', 'restore evaluation flags are missing or contradictory'
    if kind == RESTORE and event == 'restore_authorization_completed':
        decision = str(raw.get('decision', '')).strip().casefold()
        if decision == 'deny':
            return 'RESTORE_BLOCKED', 'restore authorization denied'
        if decision in ('allow', 'permit', 'approve'):
            return 'RESTORE_ENABLED', 'restore authorization granted'
        return 'UNKNOWN', 'restore authorization decision is missing or unrecognized'
    return None


def _inventory(o: Observation, kind: str):
    """A listing that names this resource, its category and a status word."""
    raw = o.raw_fields
    if o.source_type in ('txt', 'pdf') and raw.get('system_id') == o.system_id:
        category, word = raw.get('data_category'), raw.get('state')
    elif ((o.source_type == 'json' or (o.source_type == 'log' and raw.get('event') == 'record_lookup'))
          and raw.get('system') == o.system_id):
        category, word = raw.get('record_type'), raw.get('result')
    else:
        return None
    if category != INVENTORY_CATEGORY[kind] or not isinstance(word, str):
        return None
    state = INVENTORY_STATES[kind].get(word.strip().upper())
    if state is None:
        return 'UNKNOWN', f'inventory status {word!r} does not state {"connector" if kind == FLOW else "restore"} access'
    return state, f'inventory lists {category} as {word}'


def _visual(o: Observation, kind: str):
    """A screenshot record of this process from M8 (risk-only)."""
    if o.source_type != 'image': return None
    raw = o.raw_fields
    if kind != FLOW:
        return 'UNKNOWN', 'screenshot shows no explicit restore control'
    def words(names):
        return {str(raw[n]).strip().casefold() for n in names if isinstance(raw.get(n), str)}
    modes, statuses = words(VISUAL_FLOW['mode_fields']), words(VISUAL_FLOW['status_fields'])
    if modes and modes <= VISUAL_FLOW['running_modes'] and statuses and statuses <= VISUAL_FLOW['running_statuses']:
        return 'ACTIVE', 'screenshot shows a continuous connector with a running status'
    return 'UNKNOWN', 'screenshot does not show both a continuous mode and a running status'


def read(o: Observation) -> Reading | None:
    kind = observation_kind(o)
    if kind is None: return None
    if o.source_type == 'activity':
        return _claim(o, kind) if o.raw_fields.get('event_type') in CLAIM_EVENTS else None
    if o.source_type == 'audit': return None
    state, classification, explanation = _state_for_observation(o)
    when = observed_time(o)
    if state in (RISK[kind], SAFE[kind]) and classification in SAFE_PROOF:
        return Reading(o.evidence_id, o.locator, o.source_type, o.captured_at, when, state,
                       classification, explanation)
    for evidence_class, reader in (('telemetry', _telemetry), ('inventory', _inventory), ('visual', _visual)):
        found = reader(o, kind)
        if found:
            return Reading(o.evidence_id, o.locator, o.source_type, o.captured_at, when, found[0],
                           evidence_class if found[0] != 'UNKNOWN' else 'none', found[1])
    return Reading(o.evidence_id, o.locator, o.source_type, o.captured_at, when, 'UNKNOWN', 'none',
                   explanation if state == 'UNKNOWN' else f'{state} is not a {kind} state')


def admissible(o: Observation, cutoff: str, anomalies=frozenset()) -> bool:
    """Same temporal gate as M4/M5: nothing captured, emitted or recorded after
    the cutoff (or after its own capture), and nothing M1 quarantined."""
    point = parse_time(cutoff)
    if parse_time(o.captured_at) > point or (o.evidence_id, o.locator) in anomalies:
        return False
    for stamp in (o.record_time, o.event_time):
        if stamp and (parse_time(stamp) > point or parse_time(stamp) > parse_time(o.captured_at)):
            return False
    return True
