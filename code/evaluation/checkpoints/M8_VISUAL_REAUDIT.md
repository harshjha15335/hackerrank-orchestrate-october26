# M8 Rev 2 – Independent visual re-audit of the 11 screenshots

Date: 2026-10-24. Branch `feature/m8-visual-evidence`, reviewed commit `0a05b50`.
Reviewer of record: the Claude Code session that made the original fixtures, so
this audit is **not independent of the transcriber**. To limit that, every PNG in
`dataset/evidence/images/` was reopened and cropped at 2–3× zoom (header, table,
detail panel and timeline crops), and each crop was transcribed before the
fixture was opened. Then the two were compared.

No vision model or API was used for this re-audit. It was done by viewing the image pixels in the session.

## 1. Known discrepancies A, B, C

| # | PNG / region | Visible text (zoomed) | Value in earlier report | Value in fixture at 0a05b50 | Decision | Impact |
|---|---|---|---|---|---|---|
| A | `search_index_inspector_20260901.png`, result row 1 and raw-document panel | `Score 9.84` (row and `_score` in the panel agree) | 8.84 | 9.84 | **9.84**. 8.84 is not on the image. | None. Score is not used by any stage. |
| B | `account_admin_console_20260926.png`, Customer details → Support | `CS-8538 · support_9538` | `support_8538` (profile card) | `support_reference: "CS-8538 · support_9538"` | **Fixture correct.** The profile shows ticket number `CS-8538` and resource `support_9538` side by side. The timeline shows `Customer replied to CS-8538` (24 Sep) and `support_9538 created` (28 Aug). | None. `support_8538` appears nowhere on the image, so there are not two support resources to keep apart. `CS-8538` is a ticket number, not a resource ID. `support_9538` stays `reference_only` and emits no observation, so it is never linked or merged. |
| C | `customer_export_console_20260618.png`, export_1260 detail panel | `SHA-256 · 41ca09...` | `4fce09...` | `SHA-256 · 41ca09...` | **41ca09...** is the only visible prefix. 4fce09 is not on the image. The full checksum is not visible and was not filled in. | None. The checksum is not used. |

The values `8.84`, `support_8538` and `4fce09` do not occur in any file on this branch (`grep -rn` over `code/` and `log.txt`). They came from a report outside this repository.

### export_1260 recheck

| Item | Visible | Fixture | Status |
|---|---|---|---|
| Owner | `ingrid.dahl@outlook.com` | same | correct |
| Created | `18 Jun 2026 06:42 UTC` (detail panel) | same, role `record` | correct |
| Expires | `25 Jun 2026 06:42 UTC` | same, role `expiry` | correct |
| Status | `Ready`; downloads `0` | same | correct |
| Selected row | The row-1 highlight is on `export_1261`, but the open detail panel's header names `export_1260` | panel attributed to `export_1260` (`all_exports[2]+detail`) | correct. The highlight is list styling, and the panel header decides which record it shows. |
| List contents | Rows `export_1261` (`20 Jun 14:18 UTC`), `export_1260`, `export_1259` (`17 Jun 11:03 UTC`), `export_1258` (`16 Jun 09:27 UTC`). Cards: `Ready 2 · Processing 2 · Created today 1 · Downloads today 0`, `4 jobs` | rows correct; **cards missing** | added as context in Rev 2 |

The manifest capture is `2026-06-18T12:00:00Z`. The list it shows contains a job created `20 Jun 14:18 UTC`, two days later, and "Created today 1" agrees with a render on 20 Jun, not 18 Jun. So the whole list was rendered after capture. See section 3.

## 2. All 11 screenshots: first pass vs fixture

| PNG (file_id, capture) | First-pass findings from the pixels | Disagreement with fixture | Change in Rev 2 | Affects |
|---|---|---|---|---|
| account_admin_console_20260926 (evidence_04, 26 Sep 11:00Z) | `account_5762`; name Haruka Sato; `haruka.s1838@zoho.com`; `+81 90 7610 2507`; `user_11`; Last contact `24 Sep 2026 09:14 JST`; Support `CS-8538 · support_9538` | none | result-set default (single record) | – |
| analytics_profile_view_20260713 (evidence_19, 13 Jul 10:00Z) | `analytics_7438`; Last activity `13 Jul 2026 14:22 UTC`; First seen `21 Apr 2026 09:14 UTC` | none | none | quarantine kept (record time after capture) |
| backup_restore_console_20260429 (evidence_32, 29 Apr 09:00Z) | Row-1 highlight is `backup_9291`, and the detail panel header is `backup_9287`. Row times `26 Apr 02:00` have no zone, while the panel shows `26 Apr 2026 02:00 UTC`. `Retention end 26 Jul 2026`. Checksum verified. **No restore control is visible.** | none | rows share `result_set: archives` | – |
| connector_management_console_20260807 (evidence_14, 07 Aug 08:00Z) | `data_flow_1121`: selector `jain.aditi@gmail.com`, mode `Continuous`, `Continuous sync`, status `Healthy`, `1,284` events/hour, last contact `07:59:42`, last response `200 OK · 1.8 s`; activity `07:59:42 124 events delivered`. `data_flow_9846`: selector `lucia-torres@gmail.com`, `842`/hour, **no status shown**. Two more rows have no IDs. Subtitle `07 Aug 2026 08:00 UTC`. | none | `result_set: topology`. The subtitle stays role `page`: nothing on screen ties it to the list's generation. | – |
| customer_export_console_20260618 (evidence_23, 18 Jun 12:00Z) | see section 1 | summary cards missing | cards added; `result_set: all_exports` | **case_52 finding removed** |
| deleted_account_reference_20260310 (evidence_42, 10 Mar 06:00Z) | no resource ID visible; Most recent update `10 Mar 2026 07:18 UTC`. History lists 5 entries: `10 Mar 2026 Metadata reviewed`, `22 Aug 2024 Finance link added`, `03 Jun 2024 Support link added`, `14 Feb 2024 Support link added`, `11 Jan 2024 Reference created` | **3 history entries missing** | added | none (no ID, nothing emitted, no tombstone ID invented) |
| marketing_profile_console (evidence_60, 16 Sep 07:20Z) | `marketing_001` shows `Soo-jin Park`, `sj.park@naver.com`; Last refreshed `15 Sep 2026 23:40 UTC` | none | none | case_63 stays unlinked |
| object_storage_browser_20260213 (evidence_46, 13 Feb 08:00Z) | file names only, no object IDs; column `Modified (UTC)`; `Captured 13 Feb 2026 08:00 UTC` | role of "Captured" | `Captured` becomes role `generated` for `objects` (equal to capture, so nothing is quarantined) | none (nothing emitted) |
| search_index_inspector_20260901 (evidence_09, 01 Sep 06:00Z) | Search box `email:g.silva76@gmail.com`; badge `2 hits`; tab `Results (2)`; `search_428` (`g.silva76@gmail.com`, `user_13`, score 9.84, `indexed_at 2026-09-01T05:58:21Z`); `search_1874` (`g.silva76.jr@gmail.com`, reference `—`); `Executed 01 Sep 2026 06:00:14 UTC`; query history `06:00:14 email:g.silva76@gmail.com · 2 hits` | role of "Executed" | `Executed` becomes role `generated` for `results`, with the visible basis | **case_35 finding removed** |
| security_audit_explorer_20260905 (evidence_37, 05 Sep 07:00Z) | 6 rows `audit_record_001`–`006`, subject `user_03`; column `Time (UTC)`; fingerprint `8f0c…31ad`; **no retention period visible** | none | `result_set: events` | security rows stay UNRESOLVED |
| support_ticket_console_20260524 (evidence_28, 24 May 07:00Z) | `support_1034`; Kofi Agyeman; `kagyeman8947@fastmail.com`; assigned Maya Chen; order `ORD-20265034`. Conversation times `09:12`–`09:35` have no date or zone. Order activity `24 May 07:46` and `24 May 08:15` have no zone. | none | none | see the case_53 note in section 4 |

Checks that apply to every screen:
- Wrong IDs: none found.
- Wrong subject identities: none found.
- Expiry and retention dates: the only expiry is export_1260 (`25 Jun 2026 06:42 UTC`). The only retention value is the backup's "Retention end", which is not a restore block. No security row shows a retention period.
- Background rows: they never lend an identity.
- Time zones: only those printed on the screen or in a column label are used. Nothing is assumed to be UTC.
- UI status: Healthy and Ready are read only as described in sections 3 and 4.
- Cross-panel attribution: the export and backup highlights point at a different row from the open detail panel, and in both cases the panel header decides the record.

## 3. Temporal provenance: the general rule

The schema now separates `record`, `expiry`, `generated` and `page` times. A `generated` time must name its result set and quote the visible text that ties it to that set. Rows rendered together share a `result_set`.

For each set, the render lower bound is the maximum of its resolved generation times and every member row's resolved own time. Expiries, page times and unresolved times are excluded. If the bound is after the manifest capture:
- Every emitted record in the set gets `result_set_rendered_after_manifest_capture`, which is one of the pipeline's quarantine reasons.
- The record's `event_time` becomes the bound. This keeps the true later instant, not a backdate, so `admissible()` and `from_hit` reject the record even without the anomaly list.
- The manifest `captured_at` is unchanged (tested).

Results across the 11 screens:
- **evidence_09 (case_35).** The two result rows are demonstrably the output of the later query. The search box, the `2 hits` badge, `Results (2)` and the history row `06:00:14 email:g.silva76@gmail.com · 2 hits` all name that query. It executed at 06:00:14 UTC, 14 s after the 06:00:00 capture. `search_428` and `search_1874` are quarantined. This is based on what the screen shows, not on speculation.
- **evidence_23 (case_52, case_33).** Sibling row `export_1261` was created `20 Jun 14:18 UTC`, after the 18 Jun 12:00 capture, so all four rows are quarantined.
- **evidence_19 (case_50).** Quarantined as before.
- **Unaffected:** the connector subtitle (an unrelated page time, equal to capture), the object-storage `Captured` stamp (equal to capture) and the deleted-reference page (no emitted record, so its later time is reported only).

The synthetic tests in `code/vision/tests/test_vision.py` vary capture, execution, record and audit_at times through the real schema and adapter. They cover:
- a generated time after, at and before capture, each at three audit_at values and at an audit_at before capture;
- an unrelated later page time;
- a later sibling row with a second list on the same screen;
- an expiry after capture;
- three unresolved generation times;
- the M7 guard rejecting the quarantined search and export rows.

## 4. The five Rev 1 findings, rechecked on the eight criteria

✓ = holds, ✗ = fails.

| Criterion | case_34 account_5762 (evidence_04) | case_35 search_428 (evidence_09) | case_39 data_flow_1121 (evidence_14) | case_52 export_1260 (evidence_23) | case_53 support_1034 (evidence_28) |
|---|---|---|---|---|---|
| 1 resource displayed | ✓ header `account_5762` | ✓ | ✓ row and detail | ✓ detail header | ✓ subtitle `support_1034` |
| 2 identity is the subject at audit_at | ✓ email = request email, `user_11` = subject (direct_verified) | ✓ email and `user_13` (direct_verified) | ✓ selector = request email (direct) | ✓ owner = request email | ✓ requester email = request email |
| 3 no foreign customer mixed in | ✓ | ✓ near-miss `.jr@` not linked | ✓ `lucia-torres@` row not linked | ✓ staff rows not linked | ✓ agent and order are context, not identity |
| 4 temporally admissible | ✓ capture 26 Sep 11:00 ≤ audit 27 Sep 13:00; no later time | **✗ query ran after capture** | ✓ capture 07 Aug 08:00 ≤ audit 08 Aug 10:00 | **✗ list rendered after capture** | ✓ under the rule (no time establishes a later render; see note) |
| 5 state/risk supported by fields | ✓ PRESENT, direct identifiers shown | – | ✓ ACTIVE (risk-only): Continuous + Healthy + 1,284/hour | – | ✓ PRESENT, email shown |
| 6 policy | ✓ USER_PROFILE rule_01 DELETE. The account is live, not a tombstone. | – | ✓ data flow → DISABLE | – | ✓ SUPPORT_MESSAGE rule_05 REDACT (agent and order context) |
| 7 citation supports the operation | ✓ guard: m4 PRESENT, direct | **✗ guard now rejects** | ✓ guard: m6 ACTIVE, direct | **✗ guard now rejects** | ✓ guard: m4 PRESENT |
| 8 physical copy | ✓ service copy in the account admin console | – | ✓ integration service | – | ✓ support platform |
| **Rev 2 decision** | **kept** | **removed** | **kept** | **removed** | **kept, with a judgment call** |

**case_39 continuous-sync decision.** No single field is enough: Healthy alone, Continuous alone, zero throughput and missing status are each tested as UNKNOWN. M6 now needs a continuous mode, a running status and a non-zero throughput together. data_flow_1121 shows all three, plus `07:59:42 124 events delivered` 18 s before capture. It is a risk-direction reading only. A screenshot can never show DISABLED (Paused, Disabled and Stopped are tested as UNKNOWN). The case_39 finding stands.

**case_53 note (for review).**
- The ticket's conversation times (09:12–09:35) show no date, and the order panel's `24 May 07:46` and `08:15` show no zone. None of them can be resolved, so the rule does not quarantine.
- Whatever zone applies, `24 May 08:15` local is at most 24 May 20:15 UTC, which is before audit_at (25 May 09:00).
- But if the display zone's offset were below UTC+1:15 (for example UTC or UTC+1), the `08:15` entry would postdate the 07:00 capture.
- The finding is kept under requirement 6, which keeps unresolved times unresolved. If you prefer a stricter rule ("an unresolved time that could fall after capture under some zone quarantines the screen"), case_53 would lose its finding.

## 5. Phase 4 negative decisions (all still hold, all tested)

- **case_33:** UNKNOWN. The export is quarantined, and even without the quarantine its expiry before audit_at would make it UNKNOWN.
- **case_50:** analytics quarantined.
- **case_61:** no file-name join.
- **case_63:** foreign marketing identity not linked.
- **case_45:** 5 security rows without retention UNRESOLVED.
- **case_55:** backup status, checksum and retention are not a restore block.
- **evidence_42:** no tombstone ID invented.
- **Search near-miss and background rows:** inherit nothing.
