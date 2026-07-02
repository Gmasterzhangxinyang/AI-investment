---
name: data-quality-gate
description: Validate market data freshness, symbol count, trade-day count, and basic field completeness before strategy execution.
when_to_use: Use after data ingestion and before indicators/strategy logic.
inputs:
  - etf_market_raw
  - tl_market_raw
  - universe_config
outputs:
  - data_quality_report
---

Fail the workflow only on critical data issues. Warnings are surfaced in the report but do not block test runs.

