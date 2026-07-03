# AI Investment Research System

本项目是一套本地优先、规则可审计、AI 负责解释与复核的投研辅助系统。系统面向日频工作流，当前覆盖 ETF、30 年国债期货 TL 和可转债三类资产，支持 Wind Excel 模板接入、SQLite 本地存档、策略信号、数据质检、历史诊断、Excel/PDF 日报和投研问答。

> 重要声明：本系统只提供投研辅助、规则复核和数据分析能力，不构成投资建议或收益承诺。交易类结论均由确定性规则生成，AI 只解释系统已有证据，不允许新增标的、改写信号、改写排名或承诺收益。

## 交付状态

当前分支：`delivery-hardening-v1`

当前版本定位为客户试跑交付版，已完成以下稳定性要求：

- 日更流程可稳定运行，缺单个 Excel 时降级输出而不是崩溃。
- `dashboard.json` 顶层结构固定，前端、问答、导出和 SQLite 入库共用同一数据契约。
- ETF、TL、可转债均输出 `reason / metrics / rule_hits / risk_notes / confidence / data_quality`。
- QA audit 默认不阻断日报生成；只有启用 `--strict-audit` 时，audit 非 PASS 才返回非 0。
- 报告和问答使用保守话术，不出现收益承诺或过强交易表达。
- 回测统一表述为历史诊断，不包装成收益证明。
- 客户 Excel、SQLite、outputs、logs、API key 均不进入 Git。

## 资产模块

| 模块 | 当前定位 | 核心规则 | 主要输出 |
| --- | --- | --- | --- |
| ETF | 日频技术信号扫描 | MA5/MA10、MACD、前 60 日量能、客户持仓状态 | 建仓候选、平仓提示、关注池、全量信号、历史诊断 |
| TL | 30 年国债期货日频状态诊断 | 周线/日线 MACD 柱变化、KDJ 低位反弹 | 不做交易、关注交易、模型触发建仓候选、中性、数据不足 |
| 可转债 | 风险过滤后的多因子候选池 | 价格、强赎、评级、YTM、溢价率、基本面、剩余规模、行业分散 | Top10、候选池、排除清单、评分拆解、风险提示 |

详细模型文档：

- [ETF 判断逻辑、模型与公式](docs/ETF_MODEL.md)
- [TL 判断逻辑、模型与公式](docs/TL_MODEL.md)
- [可转债判断逻辑、模型与公式](docs/CONVERTIBLE_BOND_MODEL.md)
- [策略参数说明](docs/STRATEGY_PARAMETERS.md)

## 产品界面

本地 Web 工作台默认入口：

```text
http://127.0.0.1:8766/frontend/
```

主要页面：

- **投研问答**：读取日报、SQLite、策略参数和规则证据，回答投研问题。
- **每日报告**：展示今日摘要、风险提示、数据质量和报告导出入口。
- **ETF**：建仓候选、平仓提示、关注池、短期方向诊断和完整历史诊断。
- **TL**：今日状态、近期状态、规则命中和风险说明。
- **可转债**：Top10、候选池、排除清单、评分拆解和行业分散提示。
- **标的档案**：查看 ETF、TL、可转债的明细数据和触发原因。
- **数据状态**：源文件、数据库、数据质检、运行审计。
- **策略参数**：可视化调整 ETF/TL/可转债参数；保存后需刷新数据重新计算。

## 系统架构

系统的核心逻辑很简单：**Wind Excel 进入系统，确定性规则生成信号，所有结果沉淀为可审计证据；AI 只读取证据做解释，不改写交易信号。**

### 分层架构

```text
数据输入层       Wind Excel + configs
                    |
确定性计算层     数据质检 -> 指标计算 -> ETF / TL / 可转债规则
                    |
证据存储层       dashboard.json + SQLite + Excel日报 + Audit日志
                    |
产品交互层       Web工作台 + 投研问答 + PDF导出
                    |
可选AI层         只解释证据，不生成信号，不改排名
```

```text
Wind Excel / 策略参数 / 持仓状态
  -> 数据质检 / 技术指标 / ETF / TL / 可转债规则
  -> dashboard.json / SQLite / Excel日报 / Audit日志
  -> Web工作台 / 投研问答 / PDF导出
  -> 可选AI解释证据、复核口径和输出校验
```

### 日更流水线

```text
读取配置
  -> 归档源文件
  -> 读取 Excel
  -> 数据质检
  -> 计算指标
  -> 生成 ETF / TL / 可转债结果
  -> 历史诊断与风险摘要
  -> 生成 dashboard 与 Excel
  -> 写入 SQLite
```

### 代码组织

- `backend/superpower/agents/`：日更流程中的业务节点。
- `backend/superpower/skills/`：ETF、TL、可转债、质检、报告等确定性能力包。
- `backend/superpower/tools/`：Excel、PDF、LLM、文本安全等底层工具。
- `backend/superpower/chat/`：投研问答的意图识别、证据读取和输出校验。
- `backend/superpower/db/`：SQLite schema、入库和查询。
- `frontend/`：本地 Web 工作台。

## 数据输入

客户侧通过 Wind Excel 刷新数据。系统默认读取：

```text
data/wind/current/01_ETF清单和日频公式.xlsx
data/wind/current/02_TL日频公式.xlsx
data/wind/current/03_可转债数据.xlsx
```

真实客户数据不进入 Git。仓库只保留模板和示例结构：

```text
templates/
data/wind/current/.gitkeep
```

## 快速开始

建议 Python 3.12。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pandas numpy openpyxl xlsxwriter reportlab pytest
```

准备数据：

```bash
mkdir -p data/wind/current
```

把 Wind 刷新的三个 Excel 放入 `data/wind/current/`，文件名与 `configs/data_sources.json` 保持一致。

配置 OpenAI API，可选：

```bash
cp .env.example .env
```

```bash
OPENAI_API_KEY=sk-your-key-here
```

没有 API key 时，系统仍可运行；交易信号、数据质检、历史诊断、日报结构都由本地确定性规则生成，AI 解释会自动降级为本地模板。

启动本地服务：

```bash
python serve.py --port 8766
```

打开：

```text
http://127.0.0.1:8766/frontend/
```

## 手动跑日报

不通过前端时，可以直接运行：

```bash
PYTHONPATH=backend python -m superpower.cli.run_daily \
  --etf-file data/wind/current/01_ETF清单和日频公式.xlsx \
  --tl-file data/wind/current/02_TL日频公式.xlsx \
  --cb-file data/wind/current/03_可转债数据.xlsx \
  --disable-llm
```

默认行为：

- 主流程失败才返回非 0。
- QA audit 非 PASS 不阻断日报生成，只写入 `outputs/latest/audit.json` 和 `dashboard.run_info.warnings`。
- 缺 ETF、TL 或可转债单个 Excel 时，CLI 和前端刷新都会继续运行；缺失模块降级为不可用并写入数据质量提示。
- 需要交付闸门严格失败时，追加 `--strict-audit`。
- 需要跳过独立 audit 时，追加 `--skip-audit`。

## 输出文件

日更主流程输出：

```text
outputs/latest/dashboard.json
outputs/latest/audit.json
outputs/AI投研日报-Superpower-YYYYMMDD.xlsx
data/research.db
logs/agent_audit_<run_id>.jsonl
```

PDF 由前端“导出 PDF”接口生成：

```text
outputs/AI投研日报-Superpower-YYYYMMDD.pdf
```

Dashboard 固定顶层契约：

```text
run_info
data_quality
etf
tl
convertible_bond
report_summary
```

详见 [Dashboard 稳定数据契约](docs/DASHBOARD_SCHEMA.md)。

## 配置文件

```text
configs/
  data_sources.json       # Wind Excel 路径
  strategy_params.json    # ETF/TL/可转债策略参数
  model_config.json       # LLM 开关、模型和调用策略
  positions.csv           # 客户持仓状态
  universe_etf.json       # ETF 覆盖范围
  delivery.json           # 报告交付配置
```

## 项目结构

```text
backend/superpower/
  agents/                 # Agent 编排节点
  audit/                  # 独立日报审计
  chat/                   # 投研问答、证据读取、输出校验
  cli/                    # 日报命令行入口
  db/                     # SQLite schema、ingest、repository
  runtime/                # Agent runtime、Skill registry、artifact context
  server/                 # 本地 HTTP 服务
  skills/                 # 专业 Skill 包
  tools/                  # Excel/PDF/LLM/文本安全工具

frontend/
  index.html
  assets/app.js
  assets/styles.css

docs/
  DELIVERY_HARDENING.md
  DASHBOARD_SCHEMA.md
  DATA_QUALITY_RULES.md
  REPORTING_POLICY.md
  STABILITY_CHECKLIST.md

templates/                # Wind 客户模板
tests/                    # 稳定性交付测试
```

## 测试

```bash
python -m compileall backend/superpower
pytest
python tests/smoke.py
```

当前 P0 稳定性测试覆盖：

- TL 无 `code` 列时数据质检不崩。
- QA audit 默认不导致 `run_daily` 退出，`--strict-audit` 才严格失败。
- 可转债强赎未明默认不能进入 Top10。
- Wind 伪交易日和零成交量不进入指标。
- 合规否定语不会被文本安全错误替换。
- Dashboard 顶层 key 固定存在。
- ETF/TL 数据不足时降级，不输出高置信交易信号。

## 文档索引

- [客户产品说明](docs/CLIENT_PRODUCT_GUIDE.md)
- [交付加固说明](docs/DELIVERY_HARDENING.md)
- [数据质量规则](docs/DATA_QUALITY_RULES.md)
- [报告话术与合规口径](docs/REPORTING_POLICY.md)
- [稳定性交付检查表](docs/STABILITY_CHECKLIST.md)
- [项目结构说明](docs/PROJECT_STRUCTURE.md)

## 安全与隐私

以下内容不会提交到仓库：

- `.env` 和 API key。
- `data/wind/current/*.xlsx` 真实客户数据。
- `data/research.db` 和数据库备份。
- `outputs/` 生成报告。
- `logs/` 运行日志。
- Python 缓存、pytest 缓存、构建产物。

如需共享样例数据，请使用脱敏样本，不要提交客户原始 Excel。

## 当前边界

- ETF 覆盖池数量取决于客户 Excel 当前纳入标的。
- TL 当前为日频状态诊断，60 分钟频率暂未实现。
- TL 第一版不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。
- 可转债当前是单日截面打分；正式历史回测需要每日历史截面。
- 新闻、公告、宏观数据尚未作为正式数据源接入。
- 回测仅为历史诊断，不代表未来收益。

## 后续路线

- ETF 组合级资金曲线、最大回撤和参数版本化。
- TL 建仓后的平仓规则与收益诊断。
- 可转债历史截面回测。
- 公告、新闻、宏观利率和行业事件接入。
- Mac `launchd` 定时任务。
- 邮件、企业微信或飞书日报推送。
