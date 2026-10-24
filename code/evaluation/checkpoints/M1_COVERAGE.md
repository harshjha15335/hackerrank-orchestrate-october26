# M1 evidence coverage

- Manifest entries: 94
- Parsed files: 83
- Awaiting M8 multimodal extraction: 11
- Observations including activity and audit: 8569
- Canonical JSONL SHA-256: `7d025bc5d5d3dfde509f963e04a592871de599b0af2396e30a885b35fb9b1cd0`
- Source-type counts: `{'activity': 4011, 'audit': 306, 'json': 948, 'log': 2211, 'pdf': 80, 'sql': 969, 'txt': 44}`
- SQL table rows: `{'backup_restore_entries': 10, 'connector_subscriptions': 25, 'customer_analytics_profiles': 41, 'customer_data_failover_replica': 16, 'customer_data_primary': 288, 'customer_data_read_replica': 144, 'customer_data_replica_ap_south': 87, 'customer_data_replica_eu_west': 87, 'customer_data_reporting_replica': 51, 'customer_exports': 8, 'customer_profiles': 8, 'customer_profiles_failover_replica': 4, 'customer_profiles_primary': 3, 'customer_search_documents': 53, 'search_documents_primary': 3, 'security_audit_records': 30, 'snapshot_scope': 78, 'support_records': 33}`
- SQL topology rows: `{'failover': 20, 'primary': 580, 'regional': 174, 'replica': 144, 'reporting': 51}`
- Timestamp discrepancies: 2

| File ID | Source path | Format | Status | Observations |
|---|---|---|---|---:|
| evidence_01 | `evidence/logs/service_events_ap_south_20260915.log` | .log | parsed | 104 |
| evidence_02 | `evidence/records/customer_data_snapshot_bundle_20260917.json` | .json | parsed | 41 |
| evidence_03 | `evidence/records/customer_account_handover_20261001.txt` | .txt | parsed | 44 |
| evidence_04 | `evidence/images/account_admin_console_20260926.png` | .png | needs_multimodal | 0 |
| evidence_05 | `evidence/databases/customer_data_read_replica_20260921.sql` | .sql | parsed | 61 |
| evidence_06 | `evidence/logs/structured_service_events_eu_west_20260918.log` | .log | parsed | 112 |
| evidence_07 | `evidence/records/customer_data_snapshot_bundle_20260913.json` | .json | parsed | 30 |
| evidence_08 | `evidence/logs/search_index_diagnostic_20260906.log` | .log | parsed | 36 |
| evidence_09 | `evidence/images/search_index_inspector_20260901.png` | .png | needs_multimodal | 0 |
| evidence_10 | `evidence/databases/customer_data_read_replica_20260827.sql` | .sql | parsed | 59 |
| evidence_11 | `evidence/logs/syslog_archive_us_east_20260824.log` | .log | parsed | 118 |
| evidence_12 | `evidence/records/customer_data_snapshot_bundle_20260819.json` | .json | parsed | 29 |
| evidence_13 | `evidence/records/connector_configurations_20260812.json` | .json | parsed | 39 |
| evidence_14 | `evidence/images/connector_management_console_20260807.png` | .png | needs_multimodal | 0 |
| evidence_15 | `evidence/databases/customer_data_read_replica_20260802.sql` | .sql | parsed | 49 |
| evidence_16 | `evidence/logs/application_trace_ap_northeast_20260730.log` | .log | parsed | 93 |
| evidence_17 | `evidence/records/customer_data_snapshot_bundle_20260725.json` | .json | parsed | 36 |
| evidence_18 | `evidence/documents/account_history_report_20260718.pdf` | .pdf | parsed | 20 |
| evidence_19 | `evidence/images/analytics_profile_view_20260713.png` | .png | needs_multimodal | 0 |
| evidence_20 | `evidence/databases/customer_data_read_replica_20260708.sql` | .sql | parsed | 63 |
| evidence_21 | `evidence/logs/operations_stream_eu_central_20260705.log` | .log | parsed | 128 |
| evidence_22 | `evidence/records/customer_data_snapshot_bundle_20260630.json` | .json | parsed | 71 |
| evidence_23 | `evidence/images/customer_export_console_20260618.png` | .png | needs_multimodal | 0 |
| evidence_24 | `evidence/databases/customer_data_read_replica_20260613.sql` | .sql | parsed | 50 |
| evidence_25 | `evidence/logs/cloud_runtime_export_us_west_20260608.log` | .log | parsed | 128 |
| evidence_26 | `evidence/records/customer_data_snapshot_bundle_20260605.json` | .json | parsed | 32 |
| evidence_27 | `evidence/documents/legal_retention_register_20260529.pdf` | .pdf | parsed | 17 |
| evidence_28 | `evidence/images/support_ticket_console_20260524.png` | .png | needs_multimodal | 0 |
| evidence_29 | `evidence/databases/customer_data_regional_replicas_20260519.sql` | .sql | parsed | 85 |
| evidence_30 | `evidence/logs/service_events_sa_east_20260516.log` | .log | parsed | 110 |
| evidence_31 | `evidence/records/customer_data_snapshot_bundle_20260511.json` | .json | parsed | 74 |
| evidence_32 | `evidence/images/backup_restore_console_20260429.png` | .png | needs_multimodal | 0 |
| evidence_33 | `evidence/databases/customer_data_regional_replicas_20260424.sql` | .sql | parsed | 89 |
| evidence_34 | `evidence/logs/structured_service_events_ca_central_20260419.log` | .log | parsed | 136 |
| evidence_35 | `evidence/records/customer_data_snapshot_bundle_20260416.json` | .json | parsed | 28 |
| evidence_36 | `evidence/records/customer_export_manifest_20260409.json` | .json | parsed | 46 |
| evidence_37 | `evidence/images/security_audit_explorer_20260905.png` | .png | needs_multimodal | 0 |
| evidence_38 | `evidence/databases/customer_data_regional_replicas_20260330.sql` | .sql | parsed | 85 |
| evidence_39 | `evidence/logs/syslog_archive_ap_southeast_20260325.log` | .log | parsed | 114 |
| evidence_40 | `evidence/records/customer_data_snapshot_bundle_20260322.json` | .json | parsed | 31 |
| evidence_41 | `evidence/logs/notification_delivery_20260315.log` | .log | parsed | 39 |
| evidence_42 | `evidence/images/deleted_account_reference_20260310.png` | .png | needs_multimodal | 0 |
| evidence_43 | `evidence/databases/customer_data_reporting_replica_20260305.sql` | .sql | parsed | 51 |
| evidence_44 | `evidence/logs/application_trace_eu_north_20260302.log` | .log | parsed | 125 |
| evidence_45 | `evidence/records/customer_data_snapshot_bundle_20260223.json` | .json | parsed | 75 |
| evidence_46 | `evidence/images/object_storage_browser_20260213.png` | .png | needs_multimodal | 0 |
| evidence_47 | `evidence/databases/customer_data_reporting_replica_20260208.sql` | .sql | parsed | 49 |
| evidence_48 | `evidence/logs/operations_stream_me_central_20260203.log` | .log | parsed | 103 |
| evidence_49 | `evidence/records/customer_data_snapshot_bundle_20260131.json` | .json | parsed | 34 |
| evidence_50 | `evidence/records/security_audit_ledger_20261001.json` | .json | parsed | 20 |
| evidence_51 | `evidence/records/customer_data_snapshot_bundle_20260915.json` | .json | parsed | 4 |
| evidence_52 | `evidence/databases/customer_data_failover_replica_20260920.sql` | .sql | parsed | 32 |
| evidence_53 | `evidence/logs/cloud_runtime_export_af_south_20260930.log` | .log | parsed | 305 |
| evidence_54 | `evidence/databases/customer_accounts_failover_replica_20260902.sql` | .sql | parsed | 7 |
| evidence_55 | `evidence/documents/security_retention_extract.pdf` | .pdf | parsed | 18 |
| evidence_56 | `evidence/records/customer_analytics_report_20260907.json` | .json | parsed | 2 |
| evidence_57 | `evidence/databases/customer_search_primary_20260910.sql` | .sql | parsed | 3 |
| evidence_58 | `evidence/documents/delivery_correction_attachment.pdf` | .pdf | parsed | 25 |
| evidence_59 | `evidence/records/customer_export_jobs_20260914.json` | .json | parsed | 2 |
| evidence_60 | `evidence/images/marketing_profile_console.png` | .png | needs_multimodal | 0 |
| evidence_61 | `evidence/logs/support_replica.log` | .log | parsed | 10 |
| evidence_62 | `evidence/records/service_resource_export_20260129_114459.json` | .json | parsed | 34 |
| evidence_63 | `evidence/databases/customer_data_inventory_20260213.sql` | .sql | parsed | 24 |
| evidence_64 | `evidence/logs/resource_lookup_trace_20260218_083911.log` | .log | parsed | 54 |
| evidence_65 | `evidence/records/service_resource_export_20260228_103637.json` | .json | parsed | 32 |
| evidence_66 | `evidence/databases/customer_data_inventory_20260310.sql` | .sql | parsed | 31 |
| evidence_67 | `evidence/logs/resource_lookup_trace_20260310_061801.log` | .log | parsed | 4 |
| evidence_68 | `evidence/records/service_resource_export_20260320_072349.json` | .json | parsed | 31 |
| evidence_69 | `evidence/databases/customer_data_inventory_20260404.sql` | .sql | parsed | 26 |
| evidence_70 | `evidence/logs/resource_lookup_trace_20260414_054007.log` | .log | parsed | 50 |
| evidence_71 | `evidence/records/service_resource_export_20260429_083222.json` | .json | parsed | 33 |
| evidence_72 | `evidence/databases/customer_data_inventory_20260504.sql` | .sql | parsed | 28 |
| evidence_73 | `evidence/logs/resource_lookup_trace_20260509_104353.log` | .log | parsed | 68 |
| evidence_74 | `evidence/records/service_resource_export_20260514_114454.json` | .json | parsed | 30 |
| evidence_75 | `evidence/databases/customer_data_inventory_20260524.sql` | .sql | parsed | 32 |
| evidence_76 | `evidence/logs/resource_lookup_trace_20260529_074313.log` | .log | parsed | 48 |
| evidence_77 | `evidence/records/service_resource_export_20260603_083457.json` | .json | parsed | 31 |
| evidence_78 | `evidence/databases/customer_data_inventory_20260618.sql` | .sql | parsed | 26 |
| evidence_79 | `evidence/logs/resource_lookup_trace_20260623_053726.log` | .log | parsed | 60 |
| evidence_80 | `evidence/records/service_resource_export_20260628_062556.json` | .json | parsed | 29 |
| evidence_81 | `evidence/databases/customer_data_inventory_20260703.sql` | .sql | parsed | 32 |
| evidence_82 | `evidence/logs/resource_lookup_trace_20260713_093359.log` | .log | parsed | 54 |
| evidence_83 | `evidence/records/service_resource_export_20260718_104335.json` | .json | parsed | 36 |
| evidence_84 | `evidence/databases/customer_data_inventory_20260723.sql` | .sql | parsed | 34 |
| evidence_85 | `evidence/logs/resource_lookup_trace_20260728_054417.log` | .log | parsed | 46 |
| evidence_86 | `evidence/records/service_resource_export_20260807_074104.json` | .json | parsed | 28 |
| evidence_87 | `evidence/databases/customer_data_inventory_20260817.sql` | .sql | parsed | 27 |
| evidence_88 | `evidence/logs/resource_lookup_trace_20260822_103910.log` | .log | parsed | 46 |
| evidence_89 | `evidence/records/service_resource_export_20260901_053316.json` | .json | parsed | 30 |
| evidence_90 | `evidence/databases/customer_data_inventory_20260905.sql` | .sql | parsed | 1 |
| evidence_91 | `evidence/logs/resource_lookup_trace_20260911_074253.log` | .log | parsed | 62 |
| evidence_92 | `evidence/records/service_resource_export_20260915_114455.json` | .json | parsed | 40 |
| evidence_93 | `evidence/databases/customer_data_inventory_20260916.sql` | .sql | parsed | 25 |
| evidence_94 | `evidence/logs/resource_lookup_trace_20260926_103856.log` | .log | parsed | 58 |

## Timestamp discrepancies

- `evidence_13` `$.records[38]`: record_time_after_manifest_capture
- `evidence_36` `$.records[45]`: record_time_after_manifest_capture

Regenerate from the repository root with `python3 code/ingest/coverage.py > /tmp/M1_COVERAGE.md`.
The generated report contains no personal identifiers or raw evidence.
