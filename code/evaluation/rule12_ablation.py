"""Evaluation-only ablation (never production): what would change if a security
audit record with NO supplied retention period were treated as retained
(Rule 12 TRUE) instead of UNKNOWN. Quantifies the owner's policy question;
it does not decide it.

    python3 code/evaluation/rule12_ablation.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import policy.conditions as conditions
from evaluation import pre_m9_metrics as m

original = conditions.within_retention_period


def assumed_retained(d, config):
    result = original(d, config)
    if result.outcome == conditions.UNKNOWN:
        return conditions.ConditionResult(conditions.TRUE, 'ABLATION: retention assumed (no period supplied)',
                                          result.evidence)
    return result


conditions.PREDICATES['within_retention_period'] = assumed_retained
if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    cache = Path('/tmp/m4-ingest-cache')
    _, _, _, _, full = m.full_section(root / 'dataset', cache)
    sample = m.sample_section(root / 'dataset', cache)
    print(json.dumps({'strict': full['strict_validator'], 'status': full['status'], 'safety': full['safety'],
                      'citations': full['citations'], 'sha': full['sha256']['run_1'],
                      'dev': sample['with_visual']['dev'], 'holdout': sample['with_visual']['holdout']},
                     indent=1, default=str))
