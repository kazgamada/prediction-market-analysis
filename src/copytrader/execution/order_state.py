"""Order / signal state machine constants."""
from __future__ import annotations

# signals.status
SIGNAL_PENDING = "PENDING"      # waiting for execute_after
SIGNAL_EXECUTING = "EXECUTING"  # picked up by executor
SIGNAL_EXECUTED = "EXECUTED"    # CLOB POST succeeded → execution row exists
SIGNAL_SKIPPED = "SKIPPED"      # filtered by risk / paper mode / etc
SIGNAL_REJECTED = "REJECTED"    # CLOB or our preconditions said no
SIGNAL_LEGACY = "LEGACY"        # pre-Phase 1 rows

# executions.status
EXEC_PLACED = "PLACED"
EXEC_PARTIAL = "PARTIAL"
EXEC_FILLED = "FILLED"
EXEC_CANCELLED = "CANCELLED"
EXEC_REJECTED = "REJECTED"

# side
SIDE_BUY = 0
SIDE_SELL = 1
