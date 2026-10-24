# M8 – Multimodal evidence (screenshots) – Comparison Report
Date / commit: 2026-10-24 / branch `feature/m8-visual-evidence`, based on `main` at `81e98d7` (merged M7 Rev 2). The commit SHA is the branch head reported with the push.

Every number below comes from `python3 code/evaluation/m8_metrics.py` (saved as
`M8_METRICS.json` next to this file) or from the pytest run in section 4.

## 0. Starting point and provenance

- **Earlier M8 work.** The fork had no M8 branch, commit or extraction artifact. Branches on `origin` at the start: `main` (81e98d7), `feature/m0`–`m7` and `benchmark/may-winner-audit`. Any earlier Gemini M8 work exists only outside this repository, so M8 was built fresh from `81e98d7`. Nothing was overwritten.
- **How the screenshots were read.** All 11 extractions are **manual fixtures**. The Claude Code agent session that built M8 viewed each PNG directly and transcribed it to JSON. No vision model or API was called by the pipeline or by any script, because this environment has no vision API key. Each fixture says so in `provenance` (`method: manual_fixture`, `model_call: false`) and is bound to the SHA-256 of its image.
- **Actual model usage:** 0 vision model calls, 0 input tokens, 0 output tokens, $0. The extraction ledger lists 11 fixture reads on a cold run and 11 cache hits on a warm run, with `model_call=false` on every row. The M3 intent classifier still runs in its offline rules mode, so the whole pipeline also makes 0 model calls.

## 1. May reference technique
- Vision: none. `DEVELOPMENT_CHECKPOINTS.md` lists no May vision reference.
- Caching: the checkpoint plan names saai `code/agent/classifier.py:42-121` (content-hash disk cache) and leerenjie `code/cache.py`. The pattern was re-implemented, not copied, and those files were not re-read in this session. The key is `sha256(image bytes) + prompt version + provider:model`.

## 2. Our implementation
- Files: `code/vision/{schema,times,extract,adapter,main}.py`, `prompt.md`, `fixtures/*.json` (11), `tests/` (42 tests, an injection screenshot); `code/state/engine.py` (image state branch, expiry rule); `code/flow/evidence.py` (risk-only visual connector reading); `code/synthesis/main.py` (screenshots on by default, `--no-visual` ablation, `--vision-cache`); `code/evaluation/m8_metrics.py`.
- Design: an extraction is validated against a strict schema, then each **visible-ID** customer or process record becomes an M1 `Observation` (`source_type='image'`) carrying only that record's own fields. From there the observations pass through the unchanged M2 identity index, M4 latest-wins and quarantine rules, M5 policy predicates, M6 ownership and safety asymmetry, and the M7 citation guard. No stage is bypassed. A screenshot can show presence or risk, never a favourable state. See `code/vision/README.md`.

## 3. Improvements and differences
- **Strict schema with no coercion.** Unknown keys (for example `verdict` or `deletion_status`), a wrong image hash, or `model_call` contradicting the method are rejected. A model response gets one retry; a second failure yields no observations.
- **Visible-ID rule.** No resource ID is derived from a file name, title or catalog claim. This leaves three screens unused: the object-storage browser (file names only), the deleted-account reference page (no ID visible) and the support cross-reference on the account page.
- **Temporal admissibility at screen level.** Times become instants only when the screen states the date, time and zone. A record's own time after capture triggers the M1 quarantine anomaly:
  - `analytics_7438`: "Last activity 13 Jul 2026 14:22 UTC" against a 10:00 capture.
  - `export_1261`: "20 Jun 14:18 UTC" against an 18 Jun capture, with the year taken from the screen.

  Page-level times after capture are reported but not used for quarantine. This follows the M1 precedent for file-level times. It covers `evidence_09` ("Executed 06:00:14 UTC" against 06:00) and `evidence_42` ("Most recent update 10 Mar 2026 07:18 UTC" against 06:00; this screen emits nothing anyway).
- **Customer and decoy separation:**
  - Near-miss `search_1874` (`g.silva76.jr@`) is not linked to user_13.
  - Staff-owned export rows and other people's backup rows are not linked to anyone.
  - `marketing_001` shows `sj.park@naver.com`, which is not case_63's subject. A data-catalog activity claims `marketing_001` belongs to that subject, but the screen shows someone else, so nothing is linked.

## 4. Tests executed and results

| Test ID | Command | Expected | Actual | Status |
|---|---|---|---|---|
| M8-1 | `pytest code/vision -k m8_1` | 11/11 images yield valid JSON; malformed output rejected; one retry | 11/11 valid; 11 mutation cases rejected; fake-model retry gives `retries=1`, and a double failure gives `invalid=1` with no observations | PASS (on manual fixtures; no live model was exercised) |
| M8-2 | `pytest code/vision -k m8_2` | 100% field match on goldens for ≥4 screenshots | 7 screenshots checked (search, account, connector, export, marketing, security, deleted-reference). `search_428` ↔ `g.silva76@gmail.com` ↔ `user_13` is `direct_verified`; decoy `search_1874` is not linked | PASS |
| M8-3 | `pytest code/vision -k m8_3`; `python3 code/vision/main.py --cache D` twice | 2nd run: 0 calls | cold: 11 provider calls, 0 model calls; warm: 0 provider calls, 11 cache hits; a damaged cache entry is ignored | PASS |
| M8-4 | `pytest code/vision -k m8_4` | Injection image causes no behaviour change | `tests/injection_ticket.png` text is stored verbatim and reads the same as a benign ticket; an injected `deletion_status` key is rejected | PASS |
| M8-5 | `python3 code/evaluation/m8_metrics.py` | Dev and holdout with and without screenshots; keep only if holdout is not lower | delta 0.0 on every dev and holdout metric; 0 sample rows change | PASS (kept) |
| Regression | `python3 -m pytest -q -p no:cacheprovider code` | all earlier suites pass | **479 passed** (437 M0–M7 + 42 M8) | PASS |
| Ablation baseline | `python3 code/synthesis/main.py --no-visual --output X` | byte-identical to the reviewed M7 output | sha256 `aeb5c135…` (same as M7 Rev 2) | PASS |
| Determinism | two runs with screenshots | identical | sha256 `6cb5652f…` both times | PASS |

The M7 full-run tests (308 M4 unknowns, 80 rows, 120 strict errors) now pin the `--no-visual` baseline. The screenshot run is pinned in `code/vision/tests/test_vision.py`.

### Sample metrics (32 public samples; holdout is report-only and not blind)

| Split | Run | Status | Step P / R / F1 | Field acc | Seq acc | Evidence validity |
|---|---|---|---|---|---|---|
| dev (22) | without screenshots | 19/22 | 0.987 / 0.645 / 0.780 | 0.947 | 0.091 | 25/25 |
| dev (22) | with screenshots | 19/22 | 0.987 / 0.645 / 0.780 | 0.947 | 0.091 | 25/25 |
| holdout (10) | without screenshots | 9/10 | 1.000 / 0.736 / 0.848 | 0.930 | 0.000 | 26/26 |
| holdout (10) | with screenshots | 9/10 | 1.000 / 0.736 / 0.848 | 0.930 | 0.000 | 26/26 |

No sample answer cites a screenshot, and no sample row changes. `data_flow_9846` is on the connector screen with no visible status, so it gets an UNKNOWN visual reading; case_15's later heartbeat decides that case. The sample gates therefore stay where M7 left them: M5-5 (dev F1 ≥ 0.80) is **unmet at 0.780**, and M7-5 sequence accuracy is **unmet**.

### 518-case changes (with screenshots vs `--no-visual`)

7 rows change. 0 status changes: all 7 stay INCOMPLETE. 5 new findings; every screenshot citation was checked by the M7 guard, and 5/5 were accepted (811/811 citations overall).

| case | subject | before | after | why |
|---|---|---|---|---|
| case_34 | user_11 | future-only `VERIFY_RECORD_ABSENT account_5762` | FINDING `REPORT_REMAINING_RECORD account_5762` (evidence_04) + DELETE + VERIFY | the account console shows the profile with email, phone and user_11 one day before audit_at |
| case_35 | user_13 | no linked resource | FINDING `REPORT_REMAINING_RECORD search_428` (evidence_09) + DELETE + VERIFY | the search inspector shows the indexed document |
| case_39 | user_14 | no linked resource | FINDING `REPORT_ACTIVE_DATA_FLOW data_flow_1121` (evidence_14) + DISABLE + VERIFY | the connector console shows "Continuous sync", status "Healthy" (risk-only reading) |
| case_52 | user_18 | no linked resource | FINDING `REPORT_REMAINING_RECORD export_1260` (evidence_23) + DELETE + VERIFY | the export package is Ready, owned by the subject; audit is before its expiry |
| case_53 | user_22 | no linked resource | FINDING `REPORT_EXPOSED_PII support_1034` (evidence_28) + REDACT + VERIFY | the ticket shows the subject's email; assigned agent and order context make rule_05 REDACT |
| case_33 | user_18 | no linked resource | future-only `VERIFY_RECORD_ABSENT export_1260` | same export, but its visible expiry (25 Jun) precedes audit_at (19 Jul), so the state is UNKNOWN, not PRESENT |
| case_45 | user_03 | no linked resource | future-only `VERIFY_RECORD_PRESENT audit_record_003` | screen lists 6 audit rows. Only audit_record_003 has a supplied retention period (evidence_55, retain until 2027-08-25), so it is retained. The other 5 have none and stay UNRESOLVED |

### Strict validation and the 80 INCOMPLETE rows without a finding

| | without screenshots | with screenshots |
|---|---|---|
| strict M0 validator | FAIL, 120 errors in 80 rows | **FAIL, 109 errors in 75 rows** |
| nonstandard diagnostic validator | 0 errors | 0 errors |
| INCOMPLETE rows without a finding | 80 | 75 |

Reassessment of the 80 rows, using only facts the screenshots newly support:
- **5 now have an evidenced finding:** case_34, case_35, case_39, case_52, case_53.
- **2 changed shape but still have no finding:** case_33 (expiry precedes audit_at) and case_45 (5 audit rows have no retention period).
- **2 are now linked but undecided, with an unchanged output row:**
  - case_50: the analytics screen is quarantined because its own last-activity time is after capture.
  - case_55: the backup screen shows no restore control; "Retention end 26 Jul 2026" is not a restore block.
- **3 screenshot cases stay unlinked:**
  - case_61: the object-storage screen shows file names only. A catalog activity pairs `object_19` with `delivery_confirmation_19.pdf`, but that file name also appears on another person's support attachment (`support_3802` in the evidence_38 SQL replicas), so the name is not a safe join.
  - case_63: the marketing profile shows another person.
  - case_46 is COMPLETE and not in the 80. Its deleted-reference screen shows no resource ID.
- **The other 69 rows** are not touched by any screenshot.

M8 does not resolve the strict-validator failure. 75 rows still need a decision that M9/M10 must disclose.

### The 77 unknown conditional-treatment items

- **Baseline items decided by screenshot facts: 0 of 77.** No screenshot shows a retention period, legal hold or restore control for any of them.
- Within the INCOMPLETE-without-finding rows the count goes 77 → 83:
  - +5 security audit rows on the case_45 screen, which show no retention period. The owner rule keeps them UNRESOLVED.
  - +1 `analytics_7438` (case_50, quarantined).
  - +1 `backup_9287` (case_55, no restore control).
  - −1 `audit_record_3753`, because case_34 left the set while the item itself stays undecided.
- Across all 518 cases the count goes 262 → 269. Unresolved items overall go 327 → 336, and M4 UNKNOWN latest states go 308 → 312.

## 5. Known limitations and judgment calls for review
1. **No live vision inference.** Every extraction is a manual fixture made in this session. M8-1's "retried once" path is tested only with an offline fake model. If a real model is added later (M10), its usage must come from the provider's reported tokens via the ledger.
2. **Visual connector risk (M6).** Continuous mode plus a Healthy/Active/Running status is read as `ACTIVE`, class `visual`, risk-only. It decides case_39. It is never accepted as proof of a safe state.
3. **Page-level times after capture** are reported, not quarantined (`evidence_09` is 14 s after capture). Record-level times are quarantined.
4. **Time zones and years.** Times without a zone (for example the support order panel's "24 May 08:15") stay unresolved and cannot quarantine. Had they been read as UTC, the order-panel time would be after the 07:00 capture. That panel is an order, not the ticket, and is not emitted.
5. **Visible expiry** makes a later-audited export UNKNOWN (case_33) rather than PRESENT or ABSENT.
6. **File-name joins are not used** (case_61), even though a catalog activity offers one.
7. **The fixture data contains `data_flow_9846`**, a resource ID that also appears in a sample answer, because the screen shows it. Code contains no sample IDs (tested). The fixture is a transcription of every visible row, not something tuned to the answers.

## 6. Recommendation: PASS for the M8 integration gates, submission still FAIL
M8-1 through M8-5 pass, with the M8-1 caveat that only manual fixtures were exercised. The ablation keeps the screenshots: holdout is unchanged and dev is unchanged. Carried-forward gates stay FAIL: M5-5 (dev F1 0.780 < 0.80), M7-5 (sequence accuracy), strict output validation (109 errors in 75 rows) and submission readiness. Next, per the owner's plan and only when asked: M9 reporting, then M10 packaging.
