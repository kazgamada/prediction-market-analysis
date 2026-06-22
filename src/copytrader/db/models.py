"""SQLAlchemy 2 model definitions matching alembic/versions/0001_initial.py."""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


JobStatus = ENUM(
    "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED",
    name="job_status", create_type=False,
)


class Cursor(Base):
    __tablename__ = "cursors"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_block: Mapped[int] = mapped_column()
    last_block_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BlockSeen(Base):
    __tablename__ = "blocks_seen"
    block_number: Mapped[int] = mapped_column(primary_key=True)
    log_count: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Trade(Base):
    __tablename__ = "trades"
    tx_hash: Mapped[bytes] = mapped_column(LargeBinary)
    log_index: Mapped[int] = mapped_column(Integer)
    block_number: Mapped[int] = mapped_column()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exchange: Mapped[str] = mapped_column(Text)
    order_hash: Mapped[bytes] = mapped_column(LargeBinary)
    maker: Mapped[bytes] = mapped_column(LargeBinary)
    taker: Mapped[bytes] = mapped_column(LargeBinary)
    side: Mapped[int] = mapped_column(SmallInteger)
    maker_asset_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    taker_asset_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    maker_amount_filled: Mapped[Decimal] = mapped_column(Numeric(38, 0))
    taker_amount_filled: Mapped[Decimal] = mapped_column(Numeric(38, 0))
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    size_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    size_usdc: Mapped[Decimal] = mapped_column(Numeric(28, 6))
    __table_args__ = (
        PrimaryKeyConstraint("tx_hash", "log_index"),
        Index("trades_ts_idx", "ts"),
        Index("trades_block_idx", "block_number"),
        Index("trades_taker_ts_idx", "taker", text("ts DESC")),
        Index("trades_token_ts_idx", "token_id", text("ts DESC")),
    )


class WalletStatsDaily(Base):
    __tablename__ = "wallet_stats_daily"
    address: Mapped[bytes] = mapped_column(LargeBinary)
    date: Mapped[date] = mapped_column(Date)
    trades: Mapped[int] = mapped_column(Integer)
    volume_usdc: Mapped[Decimal] = mapped_column(Numeric(28, 6))
    realized_pnl_usdc: Mapped[Decimal | None] = mapped_column(Numeric(28, 6))
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    __table_args__ = (PrimaryKeyConstraint("address", "date"),)


class Watchlist(Base):
    __tablename__ = "watchlist"
    address: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    address: Mapped[bytes] = mapped_column(LargeBinary)
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    side: Mapped[int] = mapped_column(SmallInteger)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    size_usdc: Mapped[Decimal] = mapped_column(Numeric(28, 6))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text)
    # Originating trade identity (alembic 0003). De-duplicates signals at the
    # DB level: catchup and the live WS stream can both observe the same
    # OrderFilled log, and without this a single source trade would create two
    # signals -> two copy orders. Nullable so manually-injected signals (no
    # source trade) remain allowed.
    tx_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    log_index: Mapped[int | None] = mapped_column(Integer)
    # Phase 1 execution lifecycle columns (alembic 0002)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execute_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="PENDING")
    skip_reason: Mapped[str | None] = mapped_column(Text)
    execution_id: Mapped[int | None] = mapped_column()
    __table_args__ = (
        Index("signals_ts_idx", text("ts DESC")),
        Index(
            "signals_src_trade_uq",
            "tx_hash", "log_index",
            unique=True,
            postgresql_where=text("tx_hash IS NOT NULL"),
        ),
    )


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(SmallInteger)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (Index("risk_events_ts_idx", text("ts DESC")),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(JobStatus, server_default="PENDING")
    params: Mapped[dict] = mapped_column(JSONB)
    progress: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_text: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    parent_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Liveness beat (alembic 0004). Bumped on every log/progress write so the
    # lease-expiry sweep distinguishes a long-but-alive job from a dead worker
    # (a fixed started_at threshold falsely killed jobs running > the window).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("jobs_status_idx", "status", "created_at"),)


class JobLog(Base):
    __tablename__ = "job_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    level: Mapped[int] = mapped_column(SmallInteger)
    message: Mapped[str] = mapped_column(Text)
    __table_args__ = (Index("job_logs_job_ts_idx", "job_id", "ts"),)


class RpcDeadLetter(Base):
    __tablename__ = "rpc_dead_letters"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    request: Mapped[dict] = mapped_column(JSONB)
    error_text: Mapped[str] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, server_default="0")
    next_retry: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Phase 1+ tables (alembic 0002)
# ---------------------------------------------------------------------------


class MarketResolution(Base):
    __tablename__ = "market_resolutions"
    condition_id: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    outcome: Mapped[int] = mapped_column(SmallInteger)
    payout_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    clob_order_id: Mapped[str | None] = mapped_column(Text)
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    side: Mapped[int] = mapped_column(SmallInteger)
    size_usdc: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    limit_price: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    filled_size: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), server_default="0"
    )
    filled_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    fill_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signal_to_place_ms: Mapped[int | None] = mapped_column(Integer)
    place_to_fill_ms: Mapped[int | None] = mapped_column(Integer)
    error_text: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)


class Position(Base):
    __tablename__ = "positions"
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0), primary_key=True)
    market_label: Mapped[str | None] = mapped_column(Text)
    side: Mapped[int] = mapped_column(SmallInteger)
    open_size_shares: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    open_size_usdc: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    avg_price: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TradePnl(Base):
    __tablename__ = "trade_pnl"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0))
    realized_usdc: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fees_usdc: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), server_default="0"
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RiskEvaluation(Base):
    __tablename__ = "risk_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    allow_new: Mapped[bool] = mapped_column(Boolean)
    halted_reasons: Mapped[list | None] = mapped_column(JSONB)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSONB)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    cron_expr: Mapped[str] = mapped_column(Text)
    job_kind: Mapped[str] = mapped_column(Text)
    job_params: Mapped[dict] = mapped_column(JSONB)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")


class StrategyVariant(Base):
    __tablename__ = "strategy_variants"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict] = mapped_column(JSONB)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB)


class User(Base):
    __tablename__ = "users"
    id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True), primary_key=True,
                                   server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    pw_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # billing columns (added by 0007)
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text)
    subscription_status: Mapped[str | None] = mapped_column(Text)
    subscription_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_id: Mapped[str | None] = mapped_column(Text)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True), primary_key=True,
                                   server_default=text("gen_random_uuid()"))
    user_id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True),
                                        ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("sessions_token_hash_idx", "token_hash"),
        Index("sessions_user_id_idx", "user_id"),
    )


class PwResetToken(Base):
    __tablename__ = "pw_reset_tokens"
    id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True), primary_key=True,
                                   server_default=text("gen_random_uuid()"))
    user_id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True),
                                        ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True),
                                         ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPref(Base):
    __tablename__ = "notification_prefs"
    user_id: Mapped[_uuid_mod.UUID] = mapped_column(pgUUID(as_uuid=True),
                                        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    invoice_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    risk_halt: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    daily_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# AI / OpenRouter モデル選択（alembic 0009 / AUDIT.md 共通機能要件）
# ---------------------------------------------------------------------------


class AppSetting(Base):
    """管理者が UI から設定する汎用キー/値ストア（API キー等）。

    `settings`（JSONB の運用パラメータ）とは別物。こちらは管理者画面から
    入力する機微な文字列（OpenRouter API キー等）を平文 TEXT で保持し、
    `updated_by` に操作者を残して監査ログを兼ねる。読み書きはアプリ層の
    `require_admin()` でのみ許可する（本スタックは Postgres RLS 非使用）。
    """
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[_uuid_mod.UUID | None] = mapped_column(
        pgUUID(as_uuid=True), ForeignKey("users.id")
    )


class OpenRouterConfig(Base):
    """選択中の OpenRouter モデル（実質 1 件）。

    `is_selected=true` の行が常に高々 1 件になるよう部分一意インデックスで
    制約する（AUDIT.md の「トリガーで 1 件制約」を index で代替）。
    """
    __tablename__ = "openrouter_config"
    id: Mapped[_uuid_mod.UUID] = mapped_column(
        pgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    context_length: Mapped[int | None] = mapped_column(Integer)
    prompt_price_per_token: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    completion_price_per_token: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[_uuid_mod.UUID | None] = mapped_column(
        pgUUID(as_uuid=True), ForeignKey("users.id")
    )
    __table_args__ = (
        Index(
            "openrouter_config_selected_uq",
            "is_selected",
            unique=True,
            postgresql_where=text("is_selected"),
        ),
    )


class AiUsageLog(Base):
    """AI 呼び出しのトークン数・推定コストの記録（管理者ダッシュボード集計用）。"""
    __tablename__ = "ai_usage_log"
    id: Mapped[_uuid_mod.UUID] = mapped_column(
        pgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user_id: Mapped[_uuid_mod.UUID | None] = mapped_column(
        pgUUID(as_uuid=True), ForeignKey("users.id")
    )
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    endpoint: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (Index("ai_usage_log_created_idx", text("created_at DESC")),)
