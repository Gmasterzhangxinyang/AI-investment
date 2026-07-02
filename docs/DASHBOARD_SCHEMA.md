# Dashboard Schema

`outputs/latest/dashboard.json` 是前端、AI 问答、PDF 导出和 SQLite 入库共同读取的稳定数据契约。交付版保留旧字段以兼容前端，同时新增固定顶层键：

```text
run_info
data_quality
etf
tl
convertible_bond
report_summary
```

## run_info

```json
{
  "run_id": "20260702_153000",
  "trade_date": "20260626",
  "generated_at": "2026-07-02T15:30:00",
  "status": "success | partial_success",
  "llm_enabled": false,
  "disclaimer": "本报告仅为规则模型生成的投研辅助结果，不构成投资建议或收益承诺。"
}
```

## data_quality

固定包含：

- `overall_status`: `OK | WARN | ERROR`
- `checks`: 全量质检项
- `errors`: `ERROR/FAIL` 项
- `warnings`: `WARN` 项

当任一模块缺 Excel、缺字段、历史不足或没有有效交易行时，不中断报告生成，而是在这里留下可审计原因。

## etf

固定包含：

- `status`: `ok | degraded | unavailable`
- `counts`: `buy_candidates/watch/sell_alerts/all_signals`
- `buy_candidates`
- `watchlist`
- `sell_alerts`
- `signals`
- `backtest_diagnostics`

ETF 每条结论行应包含：

```text
signal_type, action, reason, metrics, rule_hits, risk_notes, confidence, data_quality
```

`signal_type` 枚举：

```text
buy_candidate | sell_alert | watch | neutral | data_unavailable
```

## tl

固定包含：

- `status`: `no_trade | attention | entry_candidate | neutral | unavailable`
- `display_status`: `不做交易 | 关注交易 | 模型触发建仓候选 | 中性 | 数据不足，无法判断`
- `today`
- `recent`
- `note`

TL 仅做状态诊断，不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。

## convertible_bond

固定包含：

- `status`: `ok | degraded | unavailable`
- `counts`: `top10/ranked_candidates/excluded`
- `top10`
- `ranked_candidates`
- `excluded`
- `industry_concentration_warning`

可转债 Top10 每行包含 `score_breakdown`，排除清单每行包含 `excluded_reason`。

## report_summary

固定包含：

- `headline`: 客户可读摘要
- `key_metrics`: 首页指标
- `top_risk_notes`: 最重要的风险提示，默认取前三条展示
- `text_safety`: 文本安全扫描结果

