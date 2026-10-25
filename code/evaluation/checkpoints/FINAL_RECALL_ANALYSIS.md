# Final recall analysis (evaluation-only; uses sample answers)

Dev recall went from 0.6446 to 0.6942. Steps: matched 84, predicted 85, gold 121.

## Missed steps by cause, after the change

| Cause | Missed steps |
|---|---|
| dev: linked: missing policy mapping | 3 |
| dev: linked: unknown conditional treatment | 12 |
| dev: linked: unknown state | 2 |
| dev: unlinked: mentioned only in evidence captured after audit_at | 2 |
| dev: unlinked: mentioned only in workflow activity rows (claims) | 8 |
| dev: unlinked: no participant evidence mentions the resource | 3 |
| dev: unlinked: only identifier-free records (positional or naming joins are not ownership) | 7 |
| holdout: unlinked: mentioned only in evidence captured after audit_at | 4 |
| holdout: unlinked: mentioned only in workflow activity rows (claims) | 5 |
| holdout: unlinked: only identifier-free records (positional or naming joins are not ownership) | 8 |

## Root-cause groups

1. **Account record known only from workflow claim rows** (VERIFY_RECORD_ABSENT for account_service; 8 dev and 5 holdout misses). The only source that ties `account_NNN` to the subject is a `deletion_worker` activity row. That row is a claim and names no user, so linking it would be a timing/claim join, which the safety rules forbid. **Not fixed.**
2. **Identifier-free records** (analytics, support, account; 7 dev). These are positional or naming joins only. **Not fixed.**
3. **Rule 05 content missing or redacted** (REDACT and REPORT_EXPOSED_PII on support messages). **Not fixed.**
4. **Rule 12 with no supplied period.** **Fixed by the owner decision** (see `FINAL_STRICT_ROOT_CAUSES.md`). 12 conditional-treatment misses remain where the record has no admissible field evidence.
5. **Evidence captured after audit_at** (2 dev). Correctly excluded.
6. **support_001 "missing policy mapping"** (3 dev). The attachment-document rule stays reverted by order.
7. **analytics_9914 unknown state** (2 dev). There is no admissible state reading.

## Per-dev-case blockers

| Case | Remaining missed steps (operation, resource, cause) |
|---|---|
| case_01 | VERIFY_RECORD_ABSENT account_001 (unlinked: mentioned only in workflow activity rows (claims)) |
| case_02 | VERIFY_RECORD_ABSENT account_002 (unlinked: mentioned only in workflow activity rows (claims)) |
| case_03 | VERIFY_RECORD_ANONYMIZED analytics_9406 (unlinked: only identifier-free records (positional or naming joins are not ownership)) |
| case_04 | VERIFY_RECORD_ABSENT account_004 (unlinked: no participant evidence mentions the resource); VERIFY_RECORD_ANONYMIZED analytics_901 (unlinked: only identifier-free records (positional or naming joins are not ownership)) |
| case_05 | none |
| case_06 | none |
| case_07 | REPORT_REMAINING_RECORD support_001 (linked: missing policy mapping); DELETE_RECORD support_001 (linked: missing policy mapping); VERIFY_RECORD_ABSENT account_007 (unlinked: mentioned only in workflow activity rows (claims)); VERIFY_RECORD_ABSENT support_001 (linked: missing policy mapping) |
| case_08 | VERIFY_RECORD_ABSENT account_008 (unlinked: mentioned only in workflow activity rows (claims)) |
| case_09 | VERIFY_RECORD_ABSENT account_3960 (unlinked: mentioned only in evidence captured after audit_at); VERIFY_RECORD_PRESENT audit_record_4902 (unlinked: mentioned only in evidence captured after audit_at) |
| case_10 | REPORT_REMAINING_RECORD support_002 (unlinked: only identifier-free records (positional or naming joins are not ownership)); DELETE_RECORD support_002 (unlinked: only identifier-free records (positional or naming joins are not ownership)); VERIFY_RECORD_ABSENT account_010 (unlinked: mentioned only in workflow activity rows (claims)); VERIFY_RECORD_ABSENT support_002 (unlinked: only identifier-free records (positional or naming joins are not ownership)) |
| case_11 | REPORT_EXPOSED_PII support_864 (linked: unknown conditional treatment); REDACT_RECORD support_864 (linked: unknown conditional treatment); VERIFY_RECORD_PRESENT audit_record_9394 (linked: unknown conditional treatment); VERIFY_RECORD_REDACTED support_864 (linked: unknown conditional treatment) |
| case_12 | REPORT_REMAINING_RECORD analytics_9914 (linked: unknown state); DELETE_RECORD analytics_9914 (linked: unknown state) |
| case_13 | VERIFY_RECORD_PRESENT audit_record_4816 (linked: unknown conditional treatment) |
| case_14 | VERIFY_RECORD_PRESENT audit_record_987 (linked: unknown conditional treatment) |
| case_15 | none |
| case_16 | none |
| case_17 | none |
| case_18 | REPORT_EXPOSED_PII support_5569 (linked: unknown conditional treatment); REDACT_RECORD support_5569 (linked: unknown conditional treatment); VERIFY_RECORD_ABSENT account_5521 (unlinked: mentioned only in workflow activity rows (claims)); VERIFY_RECORD_PRESENT audit_record_6645 (unlinked: no participant evidence mentions the resource); VERIFY_RECORD_REDACTED support_5569 (linked: unknown conditional treatment) |
| case_19 | REPORT_EXPOSED_PII support_9553 (linked: unknown conditional treatment); REDACT_RECORD support_9553 (linked: unknown conditional treatment); VERIFY_RECORD_REDACTED support_9553 (linked: unknown conditional treatment) |
| case_20 | VERIFY_RECORD_ABSENT account_5037 (unlinked: mentioned only in workflow activity rows (claims)); VERIFY_RECORD_PRESENT audit_record_5569 (unlinked: no participant evidence mentions the resource) |
| case_21 | VERIFY_RECORD_ABSENT account_6440 (unlinked: only identifier-free records (positional or naming joins are not ownership)); VERIFY_RECORD_ANONYMIZED analytics_5335 (unlinked: only identifier-free records (positional or naming joins are not ownership)) |
| case_22 | VERIFY_RECORD_ABSENT account_4990 (unlinked: mentioned only in workflow activity rows (claims)) |

Reaching 22/22 is not possible without the joins forbidden in groups 1 and 2, the content missing in group 3, or the reverted rule in group 6.
