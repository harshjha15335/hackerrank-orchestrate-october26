# M9 handoff (from the pre-M9 remediation)

Baseline for M9 is `feature/pre-m9-audit-fixes`, once Codex has re-tested it and Harsh has accepted it.

- 518 output SHA-256: `9d4e1aae…`
- Tests: 565 pass
- Strict validator: FAIL, 114 errors / 77 rows
- Dev F1: 0.798 (0.780 without the flagged document rule)
- Model calls: 0

Details are in `PRE_M9_REMEDIATION_REPORT.md` and `PRE_M9_METRICS.json`.

## Unresolved evaluation work (M9)

- `evaluation/evaluation_report.md` does not exist yet. It must report:
  - case-level status accuracy;
  - step- and field-level accuracy;
  - sequence accuracy;
  - at least three team-made evaluation cases;
  - failures found and improvements made.

  `pre_m9_metrics.py` already computes the sample metrics, miss causes and safety probes. The adversarial fixtures in the four new test files can seed the team cases.
- The holdout is not blind (10 cases were inspected). It must stay report-only and be labelled that way.
- The M5-5 / M7-5 target of dev F1 0.80 is still unmet. §4 of the report shows that the remaining gap comes from owner-decided rules (Rule 12 retention UNRESOLVED), from Rule 05 content not being observed, and from joins the project excludes (positional, timing, post-cutoff). None of these should be closed by tuning.
- The 77 strict-invalid rows need Harsh's decision on the contract question in §6 of the report before any submission claim.
- Codex should independently re-check the judgment call in §2.4 (support attachment document rule). It is in its own commit.

## Runtime AI (strategic decision, Harsh's call)

The running solution makes **0 model calls**:

- M3 intent uses offline rules, and no provider is configured.
- M8 screenshot facts are committed manual fixtures.
- Everything else is deterministic.

Whether to add a bounded AI inference component with deterministic evidence validation is undecided. Candidate uses would be ambiguous intent, screenshot extraction behind the existing schema and quarantine, or classifying Rule 05 conversation content where text exists. That decision was deliberately left open here. Any model output would have to pass the same attribution, temporal and citation guards. A model call that does not change a guarded decision adds cost without value.

## Packaging work (M10, not started)

- `code.zip` layout, README, prompts and configuration.
- `evaluation/usage_report.md`. With today's code this would honestly report 0 calls, 0 tokens and $0. It must describe the final full run that produces `output.csv`.
- Root `output.csv` is still the blank template. It is written only at M10, from the accepted pipeline.
- The chat transcript, and the AGENTS.md log, which is kept in `log.txt`.
