# Final strict-validation root causes

Strict validator: `evaluation/contract.validate_rows`, unchanged.

| Build | Errors | Invalid rows |
|---|---|---|
| Before (3a2f78a) | 114 | 77 |
| After | 42 | 33 |

## The single largest cause: Rule 12 with no supplied period

Before this change, 61 blockers were Rule 12 records with no supplied period. The pipeline left them UNKNOWN, so no treatment was decided and INCOMPLETE rows had no FINDING.

The Rule 12 change is an owner policy decision that Harsh chose on 2026-10-25. `deletion_rules.csv` has exactly one rule for SECURITY_AUDIT_LOG (`rule_12`, RETAIN "within the supplied retention period") and no rule that authorizes deleting one. An observed, subject-attributed security audit record with **no** supplied period is therefore preserved (RETAIN, verified PRESENT).

No retention period is invented. A supplied period that expired before `audit_at` is still not retained (FALSE, DELETE). A record with no admissible field evidence stays UNKNOWN.

The setting is `retention_without_period` in `code/policy/condition_bindings.json`. Setting it to `unknown` restores the earlier behaviour (518 SHA `9d4e1aae…`).

## Remaining blockers (they overlap: one row can have several)

| Blocker | Before | After |
|---|---|---|
| class 4: no admissibly linked subject-owned resource or process | 6 | 6 |
| class 4: process safe state shown only by inventory or not at all | 5 | 5 |
| class 4: rule_05: conversation content not observed (shared-context condition undecidable) | 19 | 19 |
| class 4: rule_14: no explicit restore control observed | 4 | 4 |
| class 4: treatment decided; no admissible reading of the current state | 10 | 10 |
| class 5: rule_12: no supplied retention period covering audit_at | 61 | 10 |
| class 5: rule_13: no supplied active legal hold with a basis | 1 | 1 |

Cause classes after: {"4": 23, "5": 10}. Class 5 means policy facts are undecidable from the supplied data; class 4 means evidence for the state, content, process or ownership is missing.

## Why strict zero is not reachable without fabrication

The validator requires an INCOMPLETE row to contain FINDING, REMEDIATION and VERIFICATION. Each remaining row is INCOMPLETE because a required state or treatment is unproven. Every permitted finding would assert an unproven fact:

- `REPORT_REMAINING_RECORD` / `REPORT_EXPOSED_PII` assert a PRESENT state or exposed PII that no admissible record shows.
- `REPORT_ACTIVE_DATA_FLOW` / `REPORT_RESTORE_RISK` assert an ACTIVE process.
- `DELETE_RECORD` / `REDACT_RECORD` need a decided obligation that the rule condition does not give.

Representative contradictions:

- **Rule 05 (19 blockers):** a support message whose conversation content is absent or `[REDACTED]`. Shared context can be neither confirmed (REDACT) nor excluded (DELETE).
- **Rule 14 (4):** a backup with no explicit restore control observed.
- **Process (5):** the safe state is shown only by inventory.
- **No admissible state (10):** the treatment is decided but no reading at `audit_at` exists.
- **No attributable resource (6):** no subject-owned resource is admissibly linked.
- **Rule 12 (10):** a record with no admissible field evidence.
- **Rule 13 (1):** a hold with no basis.

What would resolve them: conversation content for the Rule 05 records, restore-control and process readbacks at `audit_at`, or an organizer clarification that an INCOMPLETE row may contain verification-only or empty steps when evidence is missing.

The per-row list is in `evaluation/evaluation_report.md`, section 5. The machine-readable data is in `FINAL_METRICS.json` (`full.strict_invalid_cases`).
