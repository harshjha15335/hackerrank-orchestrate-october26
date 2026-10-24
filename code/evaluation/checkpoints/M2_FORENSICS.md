# M2 dev-sample miss forensics

- Original cited-pair retrieval: 31/38.
- Explicit SQL negative scopes: 3/3 discoverable; no user/resource association inferred.
- Remaining unattributed positive/query records: 4.
- Supported identity-linked pairs: all reached by exact or source-backed correlation.

The files below are participant evidence. Sample answers are read only by this evaluation script.

## case_01 — evidence_54 / account_001

- Source: `evidence/databases/customer_accounts_failover_replica_20260902.sql`; locator(s): `no row`.
- Resource occurs in cited source: False; class: `negative_scope_unattributed`.
- Identifier fields in cited row: `{}`.
- Resolved subject: `user_01`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('activity_3342', 'row:3343')]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `['customer_profiles_failover_replica', 'customer_profiles_primary']`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_02 — evidence_54 / account_002

- Source: `evidence/databases/customer_accounts_failover_replica_20260902.sql`; locator(s): `no row`.
- Resource occurs in cited source: False; class: `negative_scope_unattributed`.
- Identifier fields in cited row: `{}`.
- Resolved subject: `user_02`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('activity_3376', 'row:3377')]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `['customer_profiles_failover_replica', 'customer_profiles_primary']`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_03 — evidence_94 / analytics_9406

- Source: `evidence/logs/resource_lookup_trace_20260926_103856.log`; locator(s): `['line:42', 'line:43']`.
- Resource occurs in cited source: True; class: `unattributed`.
- Identifier fields in cited row: `{'customer_reference': ['None', 'null'], 'email': ['None', 'null'], 'email_hash': ['None', 'null'], 'lookup_key': ['None', 'null'], 'phone': ['None', 'null']}`.
- Resolved subject: `user_43`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('activity_3852', 'row:3853')]`; explicit trace IDs: `['rb-095409-021']`.
- Available SQL scope tables for later absence check: `[]`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_04 — evidence_54 / account_004

- Source: `evidence/databases/customer_accounts_failover_replica_20260902.sql`; locator(s): `no row`.
- Resource occurs in cited source: False; class: `negative_scope_unattributed`.
- Identifier fields in cited row: `{}`.
- Resolved subject: `user_04`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `['customer_profiles_failover_replica', 'customer_profiles_primary']`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_04 — evidence_56 / analytics_901

- Source: `evidence/records/customer_analytics_report_20260907.json`; locator(s): `['$.records[0]']`.
- Resource occurs in cited source: True; class: `unattributed`.
- Identifier fields in cited row: `{'email': ['None'], 'email_hash': ['None'], 'phone': ['None'], 'user_id': ['None']}`.
- Resolved subject: `user_04`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('activity_3463', 'row:3464')]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `[]`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_21 — evidence_92 / account_6440

- Source: `evidence/records/service_resource_export_20260915_114455.json`; locator(s): `['$.service_exports.account_service.profile_lookups[5]']`.
- Resource occurs in cited source: True; class: `unattributed`.
- Identifier fields in cited row: `{}`.
- Resolved subject: `user_21`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('activity_3661', 'row:3662')]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `[]`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.

## case_21 — evidence_92 / analytics_5335

- Source: `evidence/records/service_resource_export_20260915_114455.json`; locator(s): `['$.service_exports.analytics_platform.profiles[5]']`.
- Resource occurs in cited source: True; class: `unattributed`.
- Identifier fields in cited row: `{'customer_reference': ['None'], 'email': ['None'], 'email_hash': ['None'], 'phone': ['None']}`.
- Resolved subject: `user_21`; history fields: `['email', 'email_hash', 'phone']`; audit transitions: `[]`.
- Same resource elsewhere: `[('evidence_02', '$.snapshots[3].records[0]'), ('activity_3665', 'row:3666')]`; explicit trace IDs: `[]`.
- Available SQL scope tables for later absence check: `[]`.
- Decision: retain as scope/query evidence; no customer-specific state conclusion at M2.
