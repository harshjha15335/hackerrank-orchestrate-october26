# Final safety verification

The probes run on the 518 rows, after the change: {"accepted_citations_naming_another_person": 0, "cited_anonymized_verifications": [], "compliant_anonymize_items": 0, "delete_of_policy_retained_record": [], "delete_without_decided_delete_treatment": [], "resources_in_steps_of_more_than_one_user": []}

- Citations: 885/885 accepted, 0 rejected.
- Determinism: run 1 equals run 2 (`252b026188daea2fe4b72a5bcbaaefe4dbd98c991bc40b53ecbedd4727352e3c`).
- Ablation without visual input: `44b02147326cc0ba393033f0fd26439f83e20941375fe7a4783af598f4c6cab8`.

Invariants:

- No new join was added, so there are no new cross-customer links.
- Quarantine and the cutoff are unchanged.
- Anonymization proof is unchanged: 0 compliant ANONYMIZE items.
- RETAIN is now decided for observed security audit records with no period. These receive VERIFY_RECORD_PRESENT citing the observed record, and never a DELETE.
- Expired periods still produce DELETE.
- The support_001 attachment rule stays reverted.
- Sample answers are read only by the scorer and these evaluation scripts.

New tests are in `code/policy/tests/test_rule12_without_period.py`:

- default mode retains the record;
- an expired period is never retained;
- no field evidence gives UNKNOWN;
- `unknown` mode preserves the earlier behaviour;
- a valid supplied period still decides.

Policy fixtures that use Rule 12 to test admissibility (cutoff, other copies, other customers) run in `unknown` mode.
