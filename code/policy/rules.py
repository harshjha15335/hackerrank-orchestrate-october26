"""Load deletion_rules.csv at runtime; rule text and actions are never duplicated in code."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

ACTIONS = ('DELETE', 'REDACT', 'ANONYMIZE', 'RETAIN')
COLUMNS = ('rule_id', 'data_category', 'condition', 'required_action')
UNCONDITIONAL = 'always'


class PolicyError(ValueError):
    pass


def fingerprint(text: str) -> str:
    """Stable identity of a condition's wording, used to bind evaluators safely."""
    return hashlib.sha256(' '.join(text.split()).casefold().encode()).hexdigest()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str

    @property
    def unconditional(self) -> bool:
        return self.condition.strip().casefold() == UNCONDITIONAL

    @property
    def condition_fingerprint(self) -> str:
        return fingerprint(self.condition)


class PolicyTable:
    def __init__(self, rules: list[Rule], source: Path | None = None):
        self.rules = tuple(rules)
        self.source = source
        self.by_category: dict[str, Rule] = {}
        for rule in self.rules:
            if rule.data_category in self.by_category:
                raise PolicyError(f'duplicate policy category: {rule.data_category}')
            self.by_category[rule.data_category] = rule

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted(self.by_category))

    def rule_for(self, category: str | None) -> Rule | None:
        return self.by_category.get(category) if category else None


def load_rules(path: Path) -> PolicyTable:
    path = Path(path)
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise PolicyError(f'{path.name}: expected columns {",".join(COLUMNS)}')
        rules = []
        for number, row in enumerate(reader, 2):
            values = {k: (row[k] or '').strip() for k in COLUMNS}
            if not all(values.values()):
                raise PolicyError(f'{path.name}:{number}: empty rule field')
            if values['required_action'] not in ACTIONS:
                raise PolicyError(f'{path.name}:{number}: unknown action {values["required_action"]!r}')
            rules.append(Rule(**values))
    if len({r.rule_id for r in rules}) != len(rules):
        raise PolicyError(f'{path.name}: duplicate rule_id')
    return PolicyTable(rules, path)
