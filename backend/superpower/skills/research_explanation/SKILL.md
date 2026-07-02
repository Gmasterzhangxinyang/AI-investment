---
name: research-explanation
description: Produce professional deterministic report commentary from strategy outputs. GPT-5.5 can replace this handler in phase two.
when_to_use: Use before report generation when a concise investment summary is needed.
inputs:
  - etf_buy_candidates
  - etf_sell_alerts
  - tl_today
outputs:
  - research_summary
---

Phase one uses deterministic wording. LLM-generated commentary must never alter signals.

