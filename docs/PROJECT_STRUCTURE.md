# Project Structure

This project is a local AI research workflow for ETF, TL futures, and convertible bonds.
The trading signals are deterministic; LLMs are used only for optional review, explanation, and chat.

## Source Code

Keep these files and directories in source control.

```text
run_daily.py
serve.py
audit_daily.py
backend/
configs/
docs/
frontend/
templates/
tests/
README.md
pyproject.toml
.env.example
.gitignore
```

### backend/superpower/agents

Agent definitions and workflow contracts.
Each Agent declares its role, required inputs, produced outputs, quality gates, and decision policy.
Most Agents are `SkillBackedAgent` wrappers around a matching skill.

Daily workflow order:

```text
ConfigAgent
SourceArchiveAgent
DataAgent
PortfolioAgent
QAAgent
IndicatorAgent
ETFAgent
TLAgent
ConvertibleBondAgent
BacktestAgent
RiskAgent
AIResearchCommitteeAgent
ExplanationAgent
ReportAgent
```

### backend/superpower/skills

Business capabilities. Each skill folder contains:

```text
SKILL.md
handler.py
```

Current skills:

```text
source_archive
wind_excel_ingestion
data_quality_gate
portfolio_state_machine
technical_indicators
etf_rotation_strategy
tl_timing_strategy
convertible_bond_ranking
strategy_backtest
portfolio_risk_control
ai_research_committee
research_explanation
report_generation
```

LLM usage is limited to:

```text
ai_research_committee
research_explanation
chat/orchestrator.py
chat/agent_runtime.py
chat/evidence_review.py
```

ETF, TL, convertible bond ranking, QA, indicators, historical diagnostics, risk summary, and report generation are deterministic Python code.

### backend/superpower/runtime

Agent runtime:

```text
agent.py           AgentSpec, BaseAgent, SkillBackedAgent
context.py         shared artifact blackboard for one run
orchestrator.py    sequential workflow runner
skill_registry.py  loads skills by SKILL.md + handler.py
audit_logger.py    writes JSONL agent audit logs
artifact_store.py  atomic JSON writes and staged publication helpers
```

### backend/superpower/tools

Reusable utility layer:

```text
excel_reader.py
excel_writer.py
frame.py
llm.py
pdf_report.py
text_cleaner.py
```

### backend/superpower/db

SQLite persistence:

```text
schema.sql
ingest.py
repositories.py
connection.py
migrations.py
backup.py
```

### backend/superpower/chat

Controlled AI chat layer:

```text
orchestrator.py
router.py
tools.py
tool_registry.py
access_policy.py
agent_runtime.py
evidence_review.py
rulebook.py
guardrails.py
trace.py
schemas.py
```

The chat layer has a rule fast lane, a focused AI lane, and a bounded ReAct deep lane. Every lane builds evidence from dashboard JSON and SQLite through read-only tools. The LLM can explain only that evidence.

The current strategy and model truth is summarized in `docs/CURRENT_SYSTEM.md`. Files under `docs/superpowers/plans` and `docs/superpowers/specs` are historical implementation records.

### frontend

Local dashboard:

```text
index.html
assets/app.js
assets/styles.css
```

### configs

Runtime configuration:

```text
strategy_params.json
data_sources.json
model_config.json
positions.csv
universe_etf.json
delivery.json
```

Strategy thresholds and weights should live in `strategy_params.json`, not hard-coded inside strategy handlers.

Product guidance is documented in `docs/CLIENT_PRODUCT_GUIDE.md`.

Internal parameter meanings, tuning direction, and maintenance explanations are documented in `docs/STRATEGY_PARAMETERS.md`.

## Runtime Data

These directories are generated or local-data-specific. They are ignored by `.gitignore` and should not be mixed into source control.

```text
data/wind/current/*.xlsx       current local Wind Excel snapshots
data/archive/                  per-run source file archives and manifests
data/research.db*              local SQLite database and WAL files
data/db_backups/               database backups
logs/                          agent audit JSONL logs
outputs/                       reports, dashboard JSON, PDF, chat traces
```

Keep them for local operation and audit, but do not treat them as source code.

## Safe Cleanup

Safe to delete at any time:

```text
__pycache__/
*.pyc
.DS_Store
.pytest_cache/
```

Usually safe to archive or clear before publishing or sharing the source tree:

```text
outputs/*
logs/*
data/archive/*
data/db_backups/*
```

Do not delete without an explicit backup decision:

```text
data/wind/current/*.xlsx
data/research.db
outputs/latest/dashboard.json
outputs/latest/audit.json
latest local reports under outputs/
```

## Health Checks

Run after any cleanup or code change:

```bash
python -m compileall backend/superpower
pytest
PYTHONPATH=backend python -m superpower.cli.run_daily \
  --etf-file data/wind/current/01_ETF清单和日频公式.xlsx \
  --tl-file data/wind/current/02_TL日频公式.xlsx \
  --cb-file data/wind/current/03_可转债数据.xlsx \
  --disable-llm
```

Expected successful daily run output includes:

```text
status=success
qa_status=PASS
db_status=success
```

QA audit is non-blocking by default. A non-PASS audit writes `outputs/latest/audit.json` and dashboard warnings; it only blocks the command when `--strict-audit` is passed.
