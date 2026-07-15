# Stability Hardening

本文记录系统稳定性加固口径：不大重构、不重写策略、不引入新数据源、不让 LLM 生成交易信号，只保证本地投研流程稳定、可审计、可降级。

## 加固范围

1. 稳定运行。
   缺少单个 Excel 不阻塞全局流程；对应模块输出不可用状态和审计原因。

2. 缺数据降级。
   缺 ETF、TL 或可转债任一文件时，CLI 和前端刷新都继续运行；缺失模块写入 `data_quality` 和 `run_info.warnings`。只有全部配置的核心源 Excel 都不存在时，前端刷新才会在启动前返回错误。

3. 固定 dashboard schema。
   新增并固定 `run_info/data_quality/etf/tl/convertible_bond/report_summary` 结构，同时保留旧字段兼容前端。

4. 数据质量检查。
   缺字段、缺历史、非交易行、零成交量、重复行和无效价格均有明确质检项；TL 缺 `code` 时按日期检查重复，不崩溃。

5. ETF/TL/可转债依据字段。
   ETF、TL、可转债核心输出补充 `action/reason/metrics/rule_hits/risk_notes/confidence/data_quality`。

6. 报告安全口径。
   引入统一文本安全工具，拦截收益承诺和过强交易表述，所有报告保留免责声明。

7. 轻量历史诊断。
   历史验证统一表述为“历史诊断”，短期验证统一表述为“短期方向诊断”，并披露 T 日收盘信号、T+1 开盘执行的假设。

8. 本地数据保护。
   真实 Excel、SQLite、PDF/Excel 输出、日志和 API key 不进入 Git。

9. QA audit 稳定。
   默认 audit 非 PASS 只写入 `outputs/latest/audit.json` 和 `dashboard.run_info.warnings`；只有 `--strict-audit` 会让 audit 非 PASS 返回非 0。

10. 原子发布。
    日更先写 staging，完成 QA audit 和 SQLite ingest 后再发布；`dashboard.json` 最后切换。失败时保留上一版完整结果。

11. 刷新故障自诊断。
    刷新任务记录具体失败阶段、影响范围、旧数据保留状态和处理建议，前端不再对所有错误统一提示“检查 Excel 路径”。

12. 问答分层。
    规则查数走快速路径；普通解释走 economy model；只有跨资产或不明确问题进入受控 ReAct。白名单工具和证据复核不因加速而取消。

## 验收命令

```bash
python -m compileall backend/superpower
pytest
PYTHONPATH=backend python -m superpower.cli.run_daily \
  --etf-file data/wind/current/01_ETF清单和日频公式.xlsx \
  --tl-file data/wind/current/02_TL日频公式.xlsx \
  --cb-file data/wind/current/03_可转债数据.xlsx \
  --disable-llm
python serve.py --port 8766
```

## 当前不覆盖

- 不做 60 分钟 TL。
- 不接新闻和公告数据源。
- 不做机器学习预测。
- 不做复杂组合层资金曲线重构。
- 不允许 LLM 新增或修改交易信号。
- 不提供收益承诺。
