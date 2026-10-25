# Final exact-sequence analysis (evaluation-only)

A case is exact when its status matches and every step matches in order, field for field.

| Case | Split | Exact | Gold status | Predicted status | Gold steps | Predicted steps | Missing | Extra | Same resource and operation, different citation/state | Matched steps in gold order |
|---|---|---|---|---|---|---|---|---|---|---|
| case_01 | dev | False | COMPLETE | INCOMPLETE | 1 | 0 | 1 | 0 | 0 | True |
| case_02 | dev | False | COMPLETE | INCOMPLETE | 1 | 0 | 1 | 0 | 0 | True |
| case_03 | dev | False | COMPLETE | COMPLETE | 3 | 2 | 1 | 0 | 0 | True |
| case_04 | dev | False | COMPLETE | INCOMPLETE | 2 | 0 | 2 | 0 | 0 | True |
| case_05 | dev | True | INCOMPLETE | INCOMPLETE | 3 | 3 | 0 | 0 | 0 | True |
| case_06 | dev | True | INCOMPLETE | INCOMPLETE | 4 | 4 | 0 | 0 | 0 | True |
| case_07 | dev | False | INCOMPLETE | INCOMPLETE | 4 | 0 | 4 | 0 | 0 | True |
| case_08 | dev | False | INCOMPLETE | INCOMPLETE | 4 | 3 | 1 | 0 | 0 | True |
| case_09 | dev | False | INCOMPLETE | INCOMPLETE | 5 | 3 | 2 | 0 | 0 | True |
| case_10 | dev | False | INCOMPLETE | INCOMPLETE | 4 | 0 | 4 | 0 | 0 | True |
| case_11 | dev | False | INCOMPLETE | INCOMPLETE | 14 | 10 | 4 | 0 | 0 | True |
| case_12 | dev | False | INCOMPLETE | INCOMPLETE | 5 | 3 | 2 | 0 | 0 | True |
| case_13 | dev | False | INCOMPLETE | INCOMPLETE | 8 | 7 | 1 | 0 | 0 | True |
| case_14 | dev | False | INCOMPLETE | INCOMPLETE | 5 | 4 | 1 | 0 | 0 | True |
| case_15 | dev | True | INCOMPLETE | INCOMPLETE | 5 | 5 | 0 | 0 | 0 | True |
| case_16 | dev | True | INCOMPLETE | INCOMPLETE | 7 | 7 | 0 | 0 | 0 | True |
| case_17 | dev | False | INCOMPLETE | INCOMPLETE | 5 | 6 | 0 | 1 | 0 | True |
| case_18 | dev | False | INCOMPLETE | INCOMPLETE | 14 | 9 | 5 | 0 | 0 | True |
| case_19 | dev | False | INCOMPLETE | INCOMPLETE | 8 | 5 | 3 | 0 | 0 | True |
| case_20 | dev | False | INCOMPLETE | INCOMPLETE | 8 | 6 | 2 | 0 | 0 | True |
| case_21 | dev | False | COMPLETE | COMPLETE | 3 | 1 | 2 | 0 | 0 | True |
| case_22 | dev | False | INCOMPLETE | INCOMPLETE | 8 | 7 | 1 | 0 | 0 | True |
| case_23 | holdout (report-only) | False | INCOMPLETE | INCOMPLETE | 8 | 6 | 2 | 0 | 0 | True |
| case_24 | holdout (report-only) | False | INCOMPLETE | INCOMPLETE | 7 | 6 | 1 | 0 | 0 | True |
| case_25 | holdout (report-only) | False | COMPLETE | COMPLETE | 3 | 1 | 2 | 0 | 0 | True |
| case_26 | holdout (report-only) | False | COMPLETE | COMPLETE | 6 | 4 | 2 | 0 | 0 | True |
| case_27 | holdout (report-only) | False | COMPLETE | COMPLETE | 6 | 4 | 2 | 0 | 0 | True |
| case_28 | holdout (report-only) | False | COMPLETE | COMPLETE | 6 | 4 | 2 | 0 | 0 | True |
| case_29 | holdout (report-only) | False | INCOMPLETE | INCOMPLETE | 14 | 12 | 2 | 0 | 0 | True |
| case_30 | holdout (report-only) | False | INCOMPLETE | INCOMPLETE | 14 | 12 | 2 | 0 | 0 | True |
| case_31 | holdout (report-only) | False | COMPLETE | COMPLETE | 3 | 2 | 1 | 0 | 0 | True |
| case_32 | holdout (report-only) | False | INCOMPLETE | INCOMPLETE | 5 | 4 | 1 | 0 | 0 | True |

## Failure types (count of non-exact cases)

| Failure type | Cases |
|---|---|
| missing operation | 27 |
| extra operation | 1 |
| wrong citation/state on a matched resource+operation | 0 |
| ordering violation among matched steps | 0 |
| status mismatch | 3 |

There are no ordering violations among matched steps. Every non-exact case is missing steps, and the step_no shifts follow from those missing steps. The comparator and ordering were left unchanged. Missing steps have the causes listed in `FINAL_RECALL_ANALYSIS.md`.
