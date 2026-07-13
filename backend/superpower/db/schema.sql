CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_runs (
  run_id TEXT PRIMARY KEY,
  report_date TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  dashboard_path TEXT,
  report_path TEXT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  source_manifest_json TEXT,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS asset_master (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  first_seen_date TEXT,
  last_seen_date TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_reports (
  report_date TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  report_path TEXT,
  dashboard_path TEXT,
  summary_text TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES import_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS summary_items (
  report_date TEXT NOT NULL,
  item TEXT NOT NULL,
  value_json TEXT,
  PRIMARY KEY (report_date, item),
  FOREIGN KEY (report_date) REFERENCES daily_reports(report_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS etf_daily_bars (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  close REAL,
  ma5 REAL,
  ma10 REAL,
  ma20 REAL,
  ma60 REAL,
  vol_ratio60 REAL,
  dif REAL,
  dea REAL,
  macd_hist REAL,
  kdj_j REAL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (trade_date, code),
  FOREIGN KEY (code) REFERENCES asset_master(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS market_daily_indicators (
  asset_type TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  amount REAL,
  open_interest REAL,
  open_interest_change REAL,
  ma5 REAL,
  ma10 REAL,
  ma20 REAL,
  ma60 REAL,
  vol_ratio60 REAL,
  dif REAL,
  dea REAL,
  macd_hist REAL,
  kdj_k REAL,
  kdj_d REAL,
  kdj_j REAL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (asset_type, trade_date, code)
);

CREATE TABLE IF NOT EXISTS etf_daily_signals (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  signal_bucket TEXT NOT NULL CHECK (signal_bucket IN ('entry', 'watch', 'exit')),
  buy_signal INTEGER NOT NULL DEFAULT 0,
  sell_signal INTEGER NOT NULL DEFAULT 0,
  watch_type TEXT,
  ma5_ma10_signal TEXT,
  ma5_ma20_status TEXT,
  volume_check TEXT,
  missing_condition TEXT,
  suggested_action TEXT,
  signal_reason TEXT,
  score REAL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (trade_date, code, signal_bucket),
  FOREIGN KEY (code) REFERENCES asset_master(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tl_daily_signals (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  state TEXT,
  close REAL,
  macd_hist REAL,
  kdj_j REAL,
  week_macd_hist REAL,
  week_kdj_j REAL,
  buy_signal INTEGER NOT NULL DEFAULT 0,
  attention_signal INTEGER NOT NULL DEFAULT 0,
  no_trade_signal INTEGER NOT NULL DEFAULT 0,
  daily_macd_condition TEXT,
  daily_macd_reason TEXT,
  daily_kdj_threshold_check TEXT,
  weekly_macd_condition TEXT,
  weekly_macd_reason TEXT,
  weekly_kdj_threshold_check TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (trade_date, code),
  FOREIGN KEY (code) REFERENCES asset_master(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS convertible_bond_snapshots (
  report_date TEXT NOT NULL,
  source_date TEXT,
  bond_code TEXT NOT NULL,
  bond_name TEXT,
  record_status TEXT NOT NULL DEFAULT 'ranked',
  rank INTEGER,
  price REAL,
  remaining_years REAL,
  conversion_premium_rate REAL,
  ytm REAL,
  deducted_profit_growth REAL,
  score REAL,
  base_score REAL,
  base_grade TEXT,
  strategy_id TEXT,
  strategy_version TEXT,
  overlay_id TEXT,
  overlay_version TEXT,
  overlay_enabled INTEGER,
  config_hash TEXT,
  auxiliary_score REAL,
  auxiliary_state TEXT,
  rank_reason TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (report_date, bond_code),
  FOREIGN KEY (report_date) REFERENCES daily_reports(report_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  position_status TEXT NOT NULL,
  quantity REAL,
  cost_price REAL,
  payload_json TEXT,
  PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS data_quality_checks (
  run_id TEXT NOT NULL,
  item TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  note TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, item, detail),
  FOREIGN KEY (run_id) REFERENCES import_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_manifests (
  run_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  path TEXT,
  exists_flag INTEGER,
  size_bytes INTEGER,
  modified_at TEXT,
  sha256 TEXT,
  archive_path TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, source_type),
  FOREIGN KEY (run_id) REFERENCES import_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT NOT NULL,
  agent TEXT NOT NULL,
  status TEXT,
  message TEXT,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  metric_role TEXT,
  metric_skill TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, agent),
  FOREIGN KEY (run_id) REFERENCES import_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_reviews (
  run_id TEXT NOT NULL,
  role TEXT NOT NULL,
  title TEXT,
  llm_used INTEGER NOT NULL DEFAULT 0,
  provider TEXT,
  model TEXT,
  reason TEXT,
  review TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, role),
  FOREIGN KEY (run_id) REFERENCES import_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS risk_summary (
  report_date TEXT NOT NULL,
  item TEXT NOT NULL,
  value_json TEXT,
  level TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (report_date, item),
  FOREIGN KEY (report_date) REFERENCES daily_reports(report_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_summary (
  report_date TEXT NOT NULL,
  item TEXT NOT NULL,
  value_json TEXT,
  level TEXT,
  note TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (report_date, item),
  FOREIGN KEY (report_date) REFERENCES daily_reports(report_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_trades (
  report_date TEXT NOT NULL,
  code TEXT NOT NULL,
  entry_signal_date TEXT NOT NULL,
  name TEXT,
  entry_date TEXT,
  entry_price REAL,
  exit_signal_date TEXT,
  exit_date TEXT,
  exit_price REAL,
  holding_days INTEGER,
  gross_return REAL,
  net_return REAL,
  entry_reason TEXT,
  exit_reason TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (report_date, code, entry_signal_date),
  FOREIGN KEY (report_date) REFERENCES daily_reports(report_date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_traces (
  trace_id TEXT PRIMARY KEY,
  run_id TEXT,
  session_id TEXT,
  user_id TEXT,
  question TEXT NOT NULL,
  intent TEXT,
  answer TEXT,
  guardrail_passed INTEGER,
  llm_used INTEGER,
  llm_model TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_jobs (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed')),
  message TEXT,
  command_json TEXT,
  started_at TEXT,
  finished_at TEXT,
  return_code INTEGER,
  stdout_tail TEXT,
  stderr_tail TEXT,
  dashboard_path TEXT,
  audit_path TEXT,
  run_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_etf_daily_signals_code_date ON etf_daily_signals(code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_etf_daily_bars_code_date ON etf_daily_bars(code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_daily_indicators_code_date ON market_daily_indicators(code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_daily_indicators_type_date ON market_daily_indicators(asset_type, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_tl_daily_signals_date ON tl_daily_signals(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_import_runs_status_date ON import_runs(status, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_asset_master_type_name ON asset_master(asset_type, name);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status_created ON refresh_jobs(status, created_at DESC);
