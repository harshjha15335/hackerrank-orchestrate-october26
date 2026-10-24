"""Snapshot scope metadata for later negative-state verification (M4)."""
from dataclasses import dataclass

from ingest.evidence import parse_time


@dataclass(frozen=True)
class SnapshotScope:
    """A file/table/capture reference, without subject or state assertion."""
    evidence_id: str
    source_path: str
    table: str
    captured_at: str


class SnapshotIndex:
    """Produces scope candidates only; never confirms absence or attribution."""
    def __init__(self, observations, coverage):
        self.present = set()
        self.scopes = {}
        by_file = {o.evidence_id: o for o in observations if o.source_type == 'sql'}
        for row in coverage:
            if row['format'] != '.sql': continue
            for table in row['tables']:
                representative = by_file.get(row['file_id'])
                if representative:
                    self.scopes[(row['file_id'], table)] = SnapshotScope(
                        row['file_id'], row['source_path'], table, representative.captured_at)
        for o in observations:
            if o.source_type == 'sql' and o.resource_id:
                table = o.locator.split('[', 1)[0]
                self.present.add((o.evidence_id, table, o.resource_id))

    def scope(self, evidence_id, table, cutoff):
        entry = self.scopes.get((evidence_id, table))
        if entry and parse_time(entry.captured_at) <= parse_time(cutoff): return entry
        return None

    def absence_candidate(self, evidence_id, table, resource_id, cutoff, *, source_reference=None):
        """Return scope only with an independent source-backed resource reference.

        Even a supplied reference can belong to the wrong customer. This API
        checks neither customer attribution, snapshot completeness, source
        authority nor the correct audit-time state. M4 must establish all of
        those before treating an absent row as a confirmed absence.
        """
        if not source_reference or source_reference.resource_id != resource_id:
            return None
        scope = self.scope(evidence_id, table, cutoff)
        if scope and (evidence_id, table, resource_id) not in self.present:
            return scope
        return None
