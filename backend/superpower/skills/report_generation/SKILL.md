---
name: report-generation
description: Generate Excel report and frontend JSON payload from all strategy, risk, QA, and audit outputs.
when_to_use: Use as the final workflow skill after all strategy and risk agents finish.
inputs:
  - etf_buy_candidates
  - etf_sell_alerts
  - etf_signal_table
  - tl_today
  - tl_recent
  - data_quality_report
  - risk_summary
  - research_summary
  - agent_results
outputs:
  - report_path
  - dashboard_json_path
---

Report output is deterministic and includes Agent audit trail.

