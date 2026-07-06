# Stability Checklist

这份清单用于本地运行、发布或参数大改后的稳定性检查。每次更新代码、调整参数或更换数据模板后，都建议按项复核。

## Runtime

- [ ] `serve.py` can start.
- [ ] `run_daily` can finish with ETF、TL、可转债三个文件齐全。
- [ ] `run_daily` can finish with one missing file.
- [ ] LLM provider unavailable does not block `--disable-llm` mode.
- [ ] QA audit 非 PASS 默认不阻断日报生成。
- [ ] `--strict-audit` 下 audit FAIL 会返回非 0。

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
