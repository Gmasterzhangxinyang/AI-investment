---
name: wind-excel-ingestion
description: Read Wind-exported ETF and TL Excel workbooks, normalize them into trade-day market data tables, and reject unusable layouts.
when_to_use: Use at the start of the daily workflow when ETF/TL Excel files are available.
inputs:
  - etf_file
  - tl_file
outputs:
  - etf_market_raw
  - tl_market_raw
---

Read ETF and TL workbooks with the current Wind wide-table layout. Filter non-trading rows where volume, open, or close are zero.

