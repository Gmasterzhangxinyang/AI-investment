---
name: convertible-bond-ranking
description: Rank convertible bonds with v2 risk gates, forced-redemption checks, credit filters, fundamentals, scale, and industry diversification after convertible bond data is available.
when_to_use: Use when convertible bond data and stock fundamentals are present.
inputs:
  - cb_data
outputs:
  - cb_top10
---

If no convertible-bond file or rows are available, the skill emits empty tables
and a waiting status. Once data is present, ranking is deterministic:

1. Exclude obvious risk rows before scoring: price below 100, price not below
   140, valid forced-redemption announcement, ST underlying, weak ratings, high
   YTM credit-risk alerts, severe negative YTM, extreme conversion premium, and
   tiny remaining scale according to config. The default normal Top10 gate
   excludes A/A- and lower ratings, YTM at or below -5%, and conversion
   premium at or above 50%. A+ remains eligible as a medium-risk observation.
2. Keep but penalize rows that triggered the forced-redemption price but only
   have a no-redemption announcement or no effective announcement.
3. Score remaining bonds by winsorized fundamentals, conversion premium quality,
   YTM quality, remaining term, credit rating, forced-redemption status,
   remaining scale, and unconverted ratio. Extreme growth, negative profit base,
   high premium, and negative YTM are penalized according to config.
4. `legacy_v1` is the base decision plugin. It alone determines `base_score`,
   base grade, qualification, action, and final rank.
5. The default enabled `dynamic_v2` auxiliary overlay reads the four daily linkage
   fields and emits only an auxiliary score, state, note, data-quality result, and
   components. It cannot change exclusions, base score, qualification, action, or
   rank. LLMs can explain the resulting rows but cannot change deterministic fields.
