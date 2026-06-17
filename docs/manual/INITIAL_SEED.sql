-- Polymarket Copytrader 初期セットアップ用 settings 投入 SQL
-- USER_MANUAL.md §1.4 から参照される
-- PHASE1_LIVE_EXECUTION.md §10 と同期して更新する

-- Execution layer
INSERT INTO settings (key, value) VALUES
  ('execution_enabled',       'false'),
  ('copy_size_usdc',          '10'),
  ('copy_size_mode',          '"fixed"'),
  ('copy_delay_seconds',      '30'),
  ('order_type',              '"limit_best"'),
  ('order_tif',               '"GTC"'),
  ('limit_slippage_bps',      '100'),
  ('partial_fill_min_pct',    '0.5'),
  ('order_timeout_seconds',   '60'),

-- Risk: kill switch + halt conditions
  ('kill_switch_on',          'false'),
  ('halt_daily_pnl_pct',      '-5.0'),
  ('halt_weekly_pnl_pct',     '-8.0'),
  ('halt_consecutive_losses', '5'),
  ('halt_single_market_pct',  '25.0'),
  ('halt_indexer_lag_seconds','120'),
  ('halt_usdc_min',           '500'),
  ('halt_matic_min',          '1.0'),

-- Risk: soft limits (skip new orders but keep open)
  ('limit_total_exposure_pct','70.0'),
  ('limit_single_token_pct',  '25.0'),
  ('limit_daily_trades',      '100'),
  ('risk_loss_size_halve_at', '3'),

-- Meta-autonomy: watchlist auto rotation
  ('auto_rotate_enabled',         'true'),
  ('auto_rotate_top_n',           '15'),
  ('auto_rotate_demote_pnl_7d',   '-200.0'),
  ('auto_rotate_min_trades_7d',   '5'),
  ('auto_rotate_max_age_days',    '60'),

-- Gamma API (resolved market PnL)
  ('gamma_api_base',                '"https://gamma-api.polymarket.com"'),
  ('gamma_fetch_interval_minutes',  '60'),
  ('gamma_max_lookback_days',       '90'),

-- Rollout phase tracking
  ('rollout_phase',           '"A"'),
  ('rollout_started_at',      to_jsonb(now())),

-- Strategy (existing)
  ('rank_min_trades',         '30'),
  ('rank_min_volume_usdc',    '5000'),
  ('replay_default_delays',   '[30, 60, 120]')
ON CONFLICT (key) DO NOTHING;

-- Schedule the nightly Phase 0 cron (insert only if not exists)
INSERT INTO scheduled_jobs (name, cron_expr, job_kind, job_params, next_run_at, enabled)
VALUES
  ('nightly_phase0', '0 18 * * *', 'phase0',
   '{"window": 30, "watchlist_top": 10, "delays": [30,60,120], "copy_usd_per_trade": 50}',
   now() + interval '1 hour', true),
  ('watchlist_rotate', '0 19 * * *', 'watchlist_rotate',
   '{}', now() + interval '2 hours', true),
  ('gamma_resolve_fetch', '0 * * * *', 'gamma_resolve_fetch',
   '{}', now() + interval '5 minutes', true),
  ('daily_summary_telegram', '0 0 * * *', 'daily_summary_telegram',
   '{}', now() + interval '3 hours', true)
ON CONFLICT (name) DO NOTHING;
