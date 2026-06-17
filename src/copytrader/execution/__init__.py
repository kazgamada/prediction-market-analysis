"""Execution layer: signals → CLOB → executions → positions → trade_pnl.

Modules:
- clob_client: py-clob-client wrapper (signs + posts orders). Fail-soft if
  credentials are missing (returns dry-run results instead of raising).
- signal_consumer: watchlist OrderFilled events → signals table.
- executor: signals → risk check → CLOB POST → executions.
- position_tracker: executions FILLED → positions + trade_pnl.
- order_state: state machine constants.

Master switch: settings.execution_enabled=false → executor stops at the
"paper" stage and records the signal as SKIPPED reason="paper". This is
Phase A.
"""
