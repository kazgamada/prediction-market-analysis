"""SQLAlchemy 2 model definitions matching alembic/versions/0001_initial.py."""
from __future__ import annotations

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
    __table_args__ = (Index("signals_ts_idx", text("ts DESC")),)


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
