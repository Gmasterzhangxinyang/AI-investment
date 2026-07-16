# Stability Checklist

这份清单用于本地运行、发布或参数大改后的稳定性检查。每次更新代码、调整参数或更换数据模板后，都建议按项复核。

## Runtime

- [ ] `serve.py` can start.
- [ ] `run_daily` can finish with ETF、TL、可转债三个文件齐全。
- [ ] `run_daily` can finish with one missing file.
- [ ] LLM provider unavailable does not block `--disable-llm` mode.
- [ ] QA audit 非 PASS 默认不阻断日报生成。
- [ ] `--strict-audit` 下 audit FAIL 会返回非 0。
- [ ] 刷新期间反复读取 `outputs/latest/dashboard.json` 始终是合法完整 JSON。
- [ ] 任一发布前阶段失败时，上一版 dashboard 和报告仍可使用。
- [ ] 刷新失败能显示具体环节、影响和处理建议。

## Dashboard

- [ ] `dashboard.json` has fixed top-level keys.
- [ ] Missing module returns empty arrays or `unavailable`.
- [ ] Warnings are visible in `run_info.warnings`.
- [ ] `data_quality` contains `etf`、`tl`、`convertible_bond`.

## Data Quality

- [ ] Non-trading rows are detected.
- [ ] Zero-volume rows are excluded from indicators.
- [ ] Rows with `open/close/volume <= 0` are excluded from indicators.
- [ ] Missing columns are reported.
- [ ] Insufficient history downgrades confidence.
- [ ] ETF effective history below 60 rows cannot emit `buy_candidate`.
- [ ] TL effective history below 60 rows cannot emit `entry_candidate`.

## Reporting

- [ ] No banned phrases in PDF.
- [ ] No banned phrases in Excel.
- [ ] No banned phrases in frontend.
- [ ] Disclaimer is present.
- [ ] Historical diagnostics are described as process diagnostics, not return proof.

## ETF

- [ ] Each signal has `reason`.
- [ ] Each signal has `metrics`.
- [ ] Each signal has `rule_hits`.
- [ ] Watchlist explains missing condition.
- [ ] `action` uses the fixed enum.

## TL

- [ ] TL says state diagnosis only.
- [ ] TL status uses the fixed enum.
- [ ] `unavailable` works when data is insufficient.
- [ ] TL output does not use buy/sell recommendation wording.

## Convertible Bond

- [ ] 可转债 Top候选包含 `score_breakdown`。
- [ ] 可转债 Top候选包含 `redemption_status`。
- [ ] Excluded rows have `excluded_reason`.
- [ ] Announced redemption is hard excluded.
- [ ] Triggered redemption without valid no-redemption announcement is hard excluded by default.
- [ ] Missing redemption fields lower confidence.
- [ ] Industry concentration warning is visible when triggered.

## Historical Diagnostics

- [ ] Historical validation is called historical diagnosis.
- [ ] Short-term direction check uses T close signal and T+1 open execution assumption.
- [ ] No future return promise.
- [ ] Sample size is shown.

## Security

- [ ] No real Excel committed.
- [ ] No outputs committed.
- [ ] No SQLite committed.
- [ ] No logs committed.
- [ ] No `.env` committed.
- [ ] No API key committed.

## Chat

- [ ] 明确的单标的名称默认进入单标的详情，不误路由为全市场建仓候选。
- [ ] 收盘价、评分、量能、MACD 等明确指标走规则快速路径。
- [ ] 页面展示窗口不限制问答后台的 30 日/400 日/前 30 只分析范围。
- [ ] AI 关闭或失败时，规则支持的问题仍有确定性回答。
- [ ] 日常解释使用 economy model；跨资产深度分析才使用完整 Agent。
- [ ] AI 不能访问互联网、任意文件、SQL、写库、账户或下单接口。
- [ ] 质检总数和提醒总数不因证据明细裁剪而减少。
- [ ] 多 ETF 问题逐只返回证据，不把 `no_entry` 改写成“进入观察”。

## Documentation

- [ ] `docs/CURRENT_SYSTEM.md` 中的 active strategy 与 `configs/strategy_params.json` 一致。
- [ ] ETF、可转债和 Agent 主说明不把历史 rollout 假设写成当前默认。
- [ ] 历史 plans/specs 顶部保留“历史实施记录”标记。
- [ ] `tests/test_documentation_current.py` 通过。
