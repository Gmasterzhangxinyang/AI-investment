# Delivery Hardening

本轮 `delivery-hardening-v1` 的目标是把当前系统加固为稳定可交付版本，不大重构、不重写策略、不引入新数据源、不让 LLM 生成交易信号。

## 加固范围

1. 日更链路稳定。
   缺少单个 Excel 不阻塞全局流程；对应模块输出不可用状态和审计原因。

2. Dashboard 契约稳定。
   新增 `run_info/data_quality/etf/tl/convertible_bond/report_summary` 固定结构，同时保留旧字段兼容前端。

3. 结论证据稳定。
   ETF、TL、可转债核心输出补充 `action/reason/metrics/rule_hits/risk_notes/confidence/data_quality`。

4. 报告话术稳定。
   引入统一文本安全工具，拦截收益承诺和过强交易表述，所有报告保留免责声明。

5. 数据质量稳定。
   明确缺字段、缺历史、非交易行、零成交量、重复行、无效价格的处理口径。

6. 历史诊断稳定。
   回测统一表述为“历史回测诊断”，短期验证统一表述为“短期方向诊断”，并披露 T 日收盘信号、T+1 开盘执行的假设。

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

## 不在本轮范围

- 不做 60 分钟 TL。
- 不接新闻和公告数据源。
- 不做机器学习预测。
- 不做复杂组合层资金曲线重构。
- 不允许 LLM 新增或修改交易信号。

