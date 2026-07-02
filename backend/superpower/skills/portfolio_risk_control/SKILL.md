---
name: portfolio-risk-control
description: Create portfolio-level risk summary from positions, ETF candidates, ETF sell alerts, and TL state.
when_to_use: Use after asset strategy agents finish and before report generation.
inputs:
  - positions
  - etf_buy_candidates
  - etf_sell_alerts
  - tl_today
outputs:
  - risk_summary
---

Risk control is deterministic and must be visible in the final report.

