# Relaxed build (owner-requested; experiment/relaxed-joins)

This build is the Rule 12 retain build plus two relaxed rules that Harsh asked for ("forget my rules").

1. **Claim-linked account** (`code/state/relaxed.py`): the account_service DELETE_RECORD activity nearest the workflow's `reported_at` (within 2 hours) is treated as the subject's account. Safeguards:
   - a claim row is used by at most one request;
   - the claim is skipped if the subject already has a directly linked account;
   - the claim is skipped if any record attributes the account to someone else.

   Absence is cited from the latest complete account snapshot in the window [activity, audit_at] that has no row for the account.
2. **Rule 05 without observable content** takes the non-destructive REDACT branch (`support_without_content: redact` in `condition_bindings.json`).

| Build | Strict errors / rows | Dev F1 | Dev exact | Dev status | Holdout F1 (report-only) |
|---|---|---|---|---|---|
| baseline 3a2f78a | 114 / 77 | 0.780 | 2/22 | 19/22 | 0.848 |
| rule12-retain 78b6590 | 42 / 33 | 0.8155 | 4/22 | 19/22 | 0.866 |
| + rule 1 (claim account) | 42 / 33 | 0.8436 | 7/22 | 21/22 | 0.875 |
| + rule 2 (Rule 05 REDACT) | **27 / 20** | **0.8598** | 7/22 | 21/22 | 0.875 |

Safety probes on 518 are all 0 (no cross-user resources, no unsafe deletes, no compliant anonymizations). Citations: 962/962 accepted. The run is deterministic.

The full test suite was **not** re-run on this build because of the deadline, and the tests that encode the old rules are expected to fail. No sample answers or case IDs are used, no evidence is invented, and the validator is unchanged.
