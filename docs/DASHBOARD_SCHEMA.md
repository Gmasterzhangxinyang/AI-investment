# Dashboard Schema

`outputs/latest/dashboard.json` 是前端、AI 问答、PDF 导出和 SQLite 入库共同读取的稳定数据契约。为兼容历史前端和下游脚本，部分旧字段会继续保留，同时新增固定顶层键：

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
  "status": "success | partial_success | failed",
  "warnings": [],
  "llm_enabled": false,
  "disclaimer": "本报告仅为规则模型生成的投研辅助结果，不构成投资建议或收益承诺。"
}
```

`warnings` 会承接数据质量、文本安全和 QA audit 的非阻塞提示。默认运行下，QA audit 非 PASS 不会中断日报生成，但会写入这里；只有命令行启用 `--strict-audit` 才会让 audit 非 PASS 返回非 0。

## data_quality

固定包含：

- `overall_status`: `OK | WARN | ERROR`
- `etf`: ETF 模块质检摘要，固定包含 `status/warnings/errors`
- `tl`: TL 模块质检摘要，固定包含 `status/warnings/errors`
- `convertible_bond`: 可转债模块质检摘要，固定包含 `status/warnings/errors`
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
- `all_signals`
- `signals`
- `warnings`
- `backtest_diagnostics`

ETF 每条结论行应包含：

```text
code, name, action, display_action, reason, metrics, rule_hits, risk_notes, confidence, data_quality
```

`action` 枚举：

```text
buy_candidate | sell_alert | watch | neutral | data_unavailable
```

`metrics` 至少包含：

```text
close, ma5, ma10, ma20, macd_hist, volume_ratio_60
```

缺 ETF 文件时，`etf` key 仍然存在，数组字段返回 `[]`，`status` 为 `unavailable` 或 `degraded`。

## tl

固定包含：

- `status`: `no_trade | attention | entry_candidate | neutral | unavailable`
- `display_status`: `不做交易 | 关注交易 | 模型触发建仓候选 | 中性 | 数据不足，无法判断`
- `reason`
- `metrics`
- `rule_hits`
- `risk_notes`
- `warnings`
- `today`
- `recent`
- `note`

TL 仅做状态诊断，不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。

缺 TL 文件或有效历史不足时，`tl.status = "unavailable"`，不输出 `entry_candidate`。

## convertible_bond

固定包含：

- `status`: `ok | degraded | unavailable`
- `counts`: `top10/qualified/weak_watch/risk_watch/ranked_candidates/excluded`
- `top10`: legacy field，等于 `qualified[:10]`，不从弱观察或风险观察补足
- `qualified`: 合格候选
- `weak_watch`: 弱观察候选
- `risk_watch`: 风险观察候选
- `candidates`: 风控后全量排序
- `ranked_candidates`: 风控后全量排序兼容字段
- `excluded`: 硬排除列表
- `summary`: `qualified_count/weak_watch_count/risk_watch_count/excluded_count/top_display_title/quality_message`
- `warnings`
- `industry_concentration_warning`

可转债候选每行固定包含：

```text
rank, code, name, price, rating, premium_rate, ytm, remaining_size,
redemption_status, score, base_score, base_grade, qualification, eligible_for_top,
not_top_reason, quality_notes, score_breakdown, auxiliary_score, auxiliary_state,
auxiliary_note, auxiliary_data_quality, reason, risk_notes, confidence
```

排除清单每行至少包含：

```text
code, name, excluded_reason, qualification, eligible_for_top, not_top_reason
```

缺可转债文件时，`convertible_bond.top10 = []`，`status = "unavailable"` 或 `degraded`。

## report_summary

固定包含：

- `headline`: 用户可读摘要
- `key_points`: 用户可读要点
- `key_metrics`: 首页指标
- `risk_notes`: 最重要的风险提示，默认取前三条展示
- `top_risk_notes`: 最重要的风险提示，默认取前三条展示
- `text_safety`: 文本安全扫描结果

## confidence

统一枚举：

```text
high | medium | low
```

数据质量 WARN 至少降一级；数据质量 ERROR 不允许输出高置信交易类信号。

## 缺数据 fallback 示例

```json
{
  "run_info": {"status": "partial_success", "warnings": ["ETF文件不存在"]},
  "etf": {"buy_candidates": [], "sell_alerts": [], "watchlist": [], "all_signals": [], "warnings": ["ETF文件不存在"]},
  "tl": {"status": "unavailable", "display_status": "数据不足，无法判断", "metrics": {}, "rule_hits": [], "risk_notes": []},
  "convertible_bond": {"top10": [], "candidates": [], "excluded": [], "warnings": ["可转债文件不存在"]}
}
```
# ETF 策略状态扩展

`etf.strategy` 记录 `strategy_id`、`strategy_version` 和 `config_hash`。`etf.all_signals` 的每行同时包含 `medium_status` 与 `short_entry_status`。`etf.historical_diagnostics` 是 1/3/5/10/20 日历史表现描述，不是 P&L 回测或收益承诺。

# 可转债策略状态扩展

`convertible_bond.strategy` 记录当前基础策略与辅助层身份。候选行保留 `strategy_id/base_score/base_grade` 和 `overlay_id/auxiliary_score/auxiliary_state/auxiliary_note/auxiliary_data_quality`。当前 dynamic_v2 只做辅助，`score` 仍等于 `base_score`，排名不得由辅助字段改写。
