# Strategy Logic

## ETF

ETF assets are split by configured position state:

- Holding: evaluate sell/risk alerts
- Not holding or closed: evaluate buy candidates

Buy signals:

- MA5 crosses above MA10
- or MACD golden cross
- and volume ratio passes configured threshold

MA20 is an enhancement/explanation field, not a hard entry condition. The core moving-average relationship is MA5 versus MA10. If MA5 is also above MA20, the report labels it as an enhancement item.

Volume ratio:

```text
vol_ratio60 = today volume / average volume of the previous 60 trading days
```

Sell signals:

- close below MA10 with volume expansion
- or close below MA5 with stronger volume expansion

Ranking:

```text
score = trend * 35% + macd * 25% + volume * 25% + share_change * 15%
```

## TL

Phase one only supports daily frequency.

States:

- 不做交易
- 关注交易
- 模型触发建仓候选

Core logic:

- Weekly no-trade condition: red MACD histogram is shorter than the previous week, green histogram is longer than the previous week, or red turns green.
- Weekly attention condition: red MACD histogram is longer than the previous week, green histogram is shorter than the previous week, or green turns red.
- Weekly entry-candidate condition: weekly attention condition plus a KDJ J low below 20 within T-2 to T-1 weeks, and current weekly J is above that low.
- Daily entry-candidate condition: daily attention condition plus a KDJ J low below 5 within T-3 to T-1 days, and current daily J is above that low.
- TL has no sell signal in phase one. The system assumes no existing TL position and only gives entry timing states.

KDJ output wording:

- The displayed weekly value is "the lowest J value over the previous 2 weeks"; it is not automatically a low-position signal.
- The weekly KDJ condition is satisfied only when that value is below 20 and the current weekly J rebounds above it.
- The displayed daily value is "the lowest J value over the previous 3 days"; it is not automatically a low-position signal.
- The daily KDJ condition is satisfied only when that value is below 5 and the current daily J rebounds above it.

MACD histogram convention:

```text
red histogram = positive MACD histogram
green histogram = negative MACD histogram
attention = current histogram > previous histogram
no-trade = current histogram < previous histogram, with explicit red-to-green protection
```

Weekly signals are calculated causally as of each report date. For a Wednesday report, the current weekly bar uses data only through that Wednesday, not the future Thursday/Friday values.

## LLM boundary

When enabled and explicitly used, the configured LLM provider can write explanations from existing evidence. It cannot change signal tables, scores, historical diagnostics, or risk flags.
