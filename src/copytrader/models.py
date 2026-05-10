from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Wallet(Base):
    __tablename__ = "wallet"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    n_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_volume_usd: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    realized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    watchlisted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class Trade(Base):
    __tablename__ = "trade"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_trade_tx_log"),
        Index("ix_trade_maker_block", "maker", "block_number"),
        Index("ix_trade_taker_block", "taker", "block_number"),
        Index("ix_trade_token_block", "token_id", "block_number"),
        Index("ix_trade_block_ts", "block_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)  # 'ctf' or 'negrisk'

    order_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    maker: Mapped[str] = mapped_column(String(42), nullable=False)
    taker: Mapped[str] = mapped_column(String(42), nullable=False)
    maker_asset_id: Mapped[str] = mapped_column(String(80), nullable=False)
    taker_asset_id: Mapped[str] = mapped_column(String(80), nullable=False)
    maker_amount: Mapped[int] = mapped_column(Numeric(40, 0), nullable=False)
    taker_amount: Mapped[int] = mapped_column(Numeric(40, 0), nullable=False)
    fee: Mapped[int] = mapped_column(Numeric(40, 0), default=0)

    # Derived fields (filled at write time)
    token_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # 'BUY' or 'SELL' from taker pov
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    notional_usd: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class Market(Base):
    __tablename__ = "market"

    condition_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    question: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(255), index=True)
    outcomes_json: Mapped[str | None] = mapped_column(Text)
    clob_token_ids_json: Mapped[str | None] = mapped_column(Text)
    outcome_prices_json: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TokenIndex(Base):
    """Map outcome token_id -> condition_id + outcome_index."""

    __tablename__ = "token_index"

    token_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    condition_id: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    outcome_index: Mapped[int] = mapped_column(Integer, nullable=False)


class IngestCursor(Base):
    """Per-source progress checkpoints."""

    __tablename__ = "ingest_cursor"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Signal(Base):
    """A copy-trade signal emitted by the monitor."""

    __tablename__ = "signal"
    __table_args__ = (Index("ix_signal_detected", "detected_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_wallet: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    source_trade_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trade.id"))
    token_id: Mapped[str] = mapped_column(String(80), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    source_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    source_size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    notes: Mapped[str | None] = mapped_column(Text)


class Order(Base):
    """An order our bot placed (paper or live)."""

    __tablename__ = "order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("signal.id"))
    mode: Mapped[str] = mapped_column(String(8), nullable=False)  # 'paper' or 'live'
    clob_order_id: Mapped[str | None] = mapped_column(String(80))
    token_id: Mapped[str] = mapped_column(String(80), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    filled_size: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Position(Base):
    """Aggregated position our bot holds in a token."""

    __tablename__ = "position"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    token_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    avg_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskEvent(Base):
    __tablename__ = "risk_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    halted: Mapped[bool] = mapped_column(Boolean, default=False)


class UiState(Base):
    """UI 状態の永続化 (auto refresh トグル、最後の実行ログ、フォーム値など)。"""

    __tablename__ = "ui_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
