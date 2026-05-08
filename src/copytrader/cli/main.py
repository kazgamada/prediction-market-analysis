"""copytrader command-line interface."""

from __future__ import annotations

import asyncio
import logging

import click
from rich.console import Console
from rich.table import Table

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@click.group()
def cli() -> None:
    """Polymarket smart-money copy trader."""


# -----------------------------
# Indexing
# -----------------------------


@cli.command()
@click.option("--from-block", type=int, default=None, help="Override start block")
@click.option("--to-block", type=int, default=None, help="Override end block")
@click.option("--chunk-size", type=int, default=1000)
def backfill(from_block: int | None, to_block: int | None, chunk_size: int) -> None:
    """Backfill OrderFilled trades from Polygon into Postgres."""
    from copytrader.indexer.backfill import backfill as do_backfill

    saved = do_backfill(from_block=from_block, to_block=to_block, chunk_size=chunk_size)
    console.print(f"[green]backfill done; saved {saved} new trades")


@cli.command(name="sync-markets")
@click.option("--limit-per-page", type=int, default=500)
@click.option("--max-pages", type=int, default=None)
def sync_markets_cmd(limit_per_page: int, max_pages: int | None) -> None:
    """Sync market metadata from the Gamma API."""
    from copytrader.markets.gamma import sync_markets

    saved = sync_markets(limit_per_page=limit_per_page, max_pages=max_pages)
    console.print(f"[green]markets synced: {saved}")


# -----------------------------
# Ranking
# -----------------------------


@cli.command()
@click.option("--window", type=int, default=30, help="Lookback window in days")
@click.option("--min-trades", type=int, default=30)
@click.option("--min-volume", type=float, default=5000.0)
@click.option("--limit", type=int, default=50)
@click.option("--watchlist-top", type=int, default=0, help="Mark top N as watchlisted")
@click.option("--persist/--no-persist", default=True)
def rank(
    window: int,
    min_trades: int,
    min_volume: float,
    limit: int,
    watchlist_top: int,
    persist: bool,
) -> None:
    """Rank wallets by realized + mark-to-market PnL over a window."""
    from copytrader.ranking.pnl import persist_ranking, rank_wallets

    stats = rank_wallets(
        window_days=window,
        min_trades=min_trades,
        min_volume_usd=min_volume,
        limit=limit,
    )

    table = Table(title=f"Top wallets ({window}d)")
    table.add_column("#", justify="right")
    table.add_column("address")
    table.add_column("PnL $", justify="right")
    table.add_column("Volume $", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Score", justify="right")
    for i, s in enumerate(stats, 1):
        table.add_row(
            str(i),
            s.address,
            f"{s.pnl_usd:,.0f}",
            f"{s.volume_usd:,.0f}",
            str(s.n_trades),
            str(s.n_tokens),
            f"{s.score:,.1f}",
        )
    console.print(table)

    if persist:
        persist_ranking(stats, top_n_watchlist=watchlist_top)
        console.print(
            f"[green]persisted {len(stats)} wallets, watchlist_top={watchlist_top}"
        )


# -----------------------------
# Backtest replay
# -----------------------------


@cli.command()
@click.option("--window", type=int, default=30)
@click.option("--delays", default="30,60,120", help="Comma-separated delay seconds")
@click.option("--copy-usd", type=float, default=50.0)
@click.option("--slippage-bps", type=int, default=50)
@click.option("--top-n", type=int, default=20, help="Replay top N watchlisted/ranked wallets")
def replay(window: int, delays: str, copy_usd: float, slippage_bps: int, top_n: int) -> None:
    """Replay copy-trade strategy on historical trades for top wallets."""
    from copytrader.backtest.replay import replay_with_delays
    from copytrader.db import session_scope
    from copytrader.models import Wallet
    from sqlalchemy import select

    delay_list = [int(d.strip()) for d in delays.split(",") if d.strip()]

    with session_scope() as session:
        wallets = [
            r[0]
            for r in session.execute(
                select(Wallet.address)
                .order_by(Wallet.score.desc().nullslast())
                .limit(top_n)
            ).all()
        ]
    if not wallets:
        console.print("[red]no wallets in DB; run `copytrader rank` first")
        return

    results = replay_with_delays(
        wallets, delay_list, window_days=window, copy_size_usd=copy_usd, slippage_bps=slippage_bps
    )

    for d, rows in results.items():
        table = Table(title=f"Replay delay={d}s window={window}d copy=${copy_usd}")
        table.add_column("address")
        table.add_column("PnL $", justify="right")
        table.add_column("Realized $", justify="right")
        table.add_column("Unrealized $", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Signals", justify="right")
        table.add_column("Filled", justify="right")
        for r in rows:
            table.add_row(
                r.address,
                f"{r.total_pnl_usd:,.1f}",
                f"{r.realized_pnl_usd:,.1f}",
                f"{r.unrealized_pnl_usd:,.1f}",
                f"{r.win_rate*100:.0f}",
                str(r.n_signals),
                str(r.n_filled),
            )
        console.print(table)
        agg = sum(r.total_pnl_usd for r in rows)
        positive = sum(1 for r in rows if r.total_pnl_usd > 0)
        console.print(
            f"[bold]aggregate delay={d}s: total=${agg:,.0f} positive={positive}/{len(rows)}"
        )


# -----------------------------
# Watchlist
# -----------------------------


@cli.group()
def watch() -> None:
    """Manage the wallet watchlist."""


@watch.command("add")
@click.argument("address")
@click.option("--note", default=None)
def watch_add(address: str, note: str | None) -> None:
    from copytrader.monitor.watchlist import add

    add(address, note)
    console.print(f"[green]watchlisted {address.lower()}")


@watch.command("remove")
@click.argument("address")
def watch_remove(address: str) -> None:
    from copytrader.monitor.watchlist import remove

    remove(address)
    console.print(f"[yellow]un-watchlisted {address.lower()}")


@watch.command("list")
def watch_list() -> None:
    from copytrader.monitor.watchlist import get_watchlist

    for addr in get_watchlist():
        console.print(addr)


# -----------------------------
# Monitor / paper / live
# -----------------------------


@cli.command()
def monitor() -> None:
    """Subscribe to OrderFilled WS, persist trades, emit signals (read-only)."""
    from copytrader.monitor.detector import run as monitor_run
    from copytrader.notifier.telegram import TelegramNotifier

    notifier = TelegramNotifier()

    async def on_signal(sig):
        notifier.send(
            f"[monitor] {sig.source_wallet[:8]}… {sig.side} "
            f"`{sig.token_id[:10]}…` size={sig.source_size} @ {sig.source_price}"
        )

    asyncio.run(monitor_run(on_signal=on_signal))


@cli.command()
@click.option("--copy-usd", type=float, default=5.0)
@click.option("--max-order-usd", type=float, default=10.0)
@click.option("--max-position-usd", type=float, default=50.0)
@click.option("--max-total-usd", type=float, default=200.0)
@click.option("--max-daily-loss-usd", type=float, default=20.0)
def paper(
    copy_usd: float,
    max_order_usd: float,
    max_position_usd: float,
    max_total_usd: float,
    max_daily_loss_usd: float,
) -> None:
    """Live monitor + paper-trade executor (no real orders)."""
    from copytrader.executor.sizing import CopyConfig
    from copytrader.executor.trader import Trader
    from copytrader.monitor.detector import run as monitor_run
    from copytrader.notifier.telegram import TelegramNotifier
    from copytrader.risk.limits import RiskLimits

    trader = Trader(
        mode="paper",
        copy_cfg=CopyConfig(fixed_usd=copy_usd, max_usd=max_order_usd),
        limits=RiskLimits(
            max_order_usd=max_order_usd,
            max_position_usd_per_token=max_position_usd,
            max_total_exposure_usd=max_total_usd,
            max_daily_loss_usd=max_daily_loss_usd,
        ),
    )
    notifier = TelegramNotifier()

    async def on_signal(sig):
        order = trader.handle_signal(sig.id)
        if order:
            notifier.send(
                f"[paper] {sig.side} `{sig.token_id[:10]}…` size={order.size} "
                f"@ {order.avg_fill_price or order.limit_price} status={order.status}"
            )

    asyncio.run(monitor_run(on_signal=on_signal))


@cli.command()
@click.option("--copy-usd", type=float, default=5.0)
@click.option("--max-order-usd", type=float, default=5.0)
@click.option("--max-position-usd", type=float, default=20.0)
@click.option("--max-total-usd", type=float, default=50.0)
@click.option("--max-daily-loss-usd", type=float, default=20.0)
@click.option(
    "--i-understand-the-risk",
    is_flag=True,
    help="Required to enable live order placement.",
)
def live(
    copy_usd: float,
    max_order_usd: float,
    max_position_usd: float,
    max_total_usd: float,
    max_daily_loss_usd: float,
    i_understand_the_risk: bool,
) -> None:
    """Live monitor + LIVE executor. Real money. Gated behind --i-understand-the-risk."""
    if not i_understand_the_risk:
        click.echo(
            "Refusing to start live mode without --i-understand-the-risk. "
            "Run `copytrader paper` first and verify caps.",
            err=True,
        )
        raise SystemExit(2)

    from copytrader.executor.sizing import CopyConfig
    from copytrader.executor.trader import Trader
    from copytrader.monitor.detector import run as monitor_run
    from copytrader.notifier.telegram import TelegramNotifier
    from copytrader.risk.limits import RiskLimits

    trader = Trader(
        mode="live",
        copy_cfg=CopyConfig(fixed_usd=copy_usd, max_usd=max_order_usd),
        limits=RiskLimits(
            max_order_usd=max_order_usd,
            max_position_usd_per_token=max_position_usd,
            max_total_exposure_usd=max_total_usd,
            max_daily_loss_usd=max_daily_loss_usd,
        ),
    )
    notifier = TelegramNotifier()
    notifier.send(
        f"*LIVE MODE STARTED* caps: order=${max_order_usd} pos=${max_position_usd} "
        f"total=${max_total_usd} daily_loss=${max_daily_loss_usd}"
    )

    async def on_signal(sig):
        order = trader.handle_signal(sig.id)
        if order:
            notifier.send(
                f"[live] {sig.side} `{sig.token_id[:10]}…` size={order.size} "
                f"@ {order.limit_price} status={order.status} clob={order.clob_order_id}"
            )

    # Periodic background tasks: order status poll + on-chain reconcile
    from decimal import Decimal

    from copytrader.executor.poller import poll_open_orders
    from copytrader.executor.reconciler import reconcile_live

    async def poll_task():
        await asyncio.to_thread(poll_open_orders, trader._clob)

    async def reconcile_task():
        await asyncio.to_thread(reconcile_live, trader.state, Decimal("0.5"), True)

    periodic = [
        ("poller", 30.0, poll_task),
        ("reconciler", 300.0, reconcile_task),
    ]
    asyncio.run(monitor_run(on_signal=on_signal, periodic_tasks=periodic))


# -----------------------------
# Status / utilities
# -----------------------------


@cli.command()
def status() -> None:
    """Print recent signals, open positions, and risk events."""
    from copytrader.db import session_scope
    from copytrader.models import Position, RiskEvent, Signal
    from sqlalchemy import select

    with session_scope() as session:
        signals = session.execute(
            select(Signal).order_by(Signal.detected_at.desc()).limit(10)
        ).scalars().all()
        positions = session.execute(
            select(Position).where(Position.closed_at.is_(None))
        ).scalars().all()
        risk = session.execute(
            select(RiskEvent).order_by(RiskEvent.occurred_at.desc()).limit(5)
        ).scalars().all()

        sig_table = Table(title="Recent signals")
        for c in ("when", "wallet", "side", "token", "size", "status"):
            sig_table.add_column(c)
        for s in signals:
            sig_table.add_row(
                s.detected_at.strftime("%H:%M:%S"),
                s.source_wallet[:10],
                s.side,
                s.token_id[:10],
                f"{s.source_size}",
                s.status,
            )
        console.print(sig_table)

        pos_table = Table(title="Open positions")
        for c in ("mode", "token", "size", "avg", "realized"):
            pos_table.add_column(c)
        for p in positions:
            pos_table.add_row(
                p.mode,
                p.token_id[:10],
                f"{p.size}",
                f"{p.avg_entry_price}",
                f"{p.realized_pnl}",
            )
        console.print(pos_table)

        if risk:
            r_table = Table(title="Recent risk events")
            for c in ("when", "kind", "halted", "detail"):
                r_table.add_column(c)
            for r in risk:
                r_table.add_row(
                    r.occurred_at.strftime("%m-%d %H:%M"),
                    r.kind,
                    "Y" if r.halted else "",
                    (r.detail or "")[:80],
                )
            console.print(r_table)


@cli.command()
@click.option("--no-trip", is_flag=True, help="Log mismatches but do not flip the killswitch")
def reconcile(no_trip: bool) -> None:
    """One-shot: compare DB live positions vs on-chain CTF balances."""
    from copytrader.executor.reconciler import reconcile_live
    from copytrader.risk.limits import RiskState

    state = RiskState()
    diffs = reconcile_live(state=state, trip_on_mismatch=not no_trip)
    if not diffs:
        console.print("[green]all live positions match on-chain")
        return
    table = Table(title="Reconcile mismatches")
    for c in ("token", "expected", "actual", "diff"):
        table.add_column(c, justify="right")
    for d in diffs:
        table.add_row(d.token_id[:14], f"{d.expected}", f"{d.actual}", f"{d.diff}")
    console.print(table)
    if state.halted:
        console.print(f"[red]killswitch tripped: {state.halt_reason}")


@cli.command()
def poll() -> None:
    """One-shot: refresh status of open live orders from the CLOB."""
    from copytrader.executor.poller import poll_open_orders

    n = poll_open_orders()
    console.print(f"[green]polled and updated {n} orders")


@cli.command()
@click.argument("address")
@click.option("--window", type=int, default=30)
@click.option("--limit", type=int, default=20)
def inspect(address: str, window: int, limit: int) -> None:
    """Inspect a wallet's per-token PnL and recent activity."""
    from copytrader.analysis.wallets import stats

    rows = stats(address, window_days=window)
    if not rows:
        console.print(f"[yellow]no trades for {address} in last {window}d")
        return
    table = Table(title=f"{address.lower()} ({window}d)")
    for c in ("token", "n", "PnL $", "net USDC", "net tokens", "mark", "last"):
        table.add_column(c, justify="right")
    total = 0.0
    for r in rows[:limit]:
        total += r.pnl_usd
        last_str = r.last_trade_at.strftime("%m-%d %H:%M") if r.last_trade_at else "-"
        table.add_row(
            r.token_id[:14],
            str(r.n_trades),
            f"{r.pnl_usd:,.2f}",
            f"{r.net_usdc:,.2f}",
            f"{r.net_tokens:,.2f}",
            f"{r.mark_price:.3f}",
            last_str,
        )
    console.print(table)
    console.print(f"[bold]total displayed PnL: ${total:,.2f}  (rows: {min(limit, len(rows))}/{len(rows)})")


@cli.command()
def balance() -> None:
    """Show on-chain USDC and CTF balances for the configured wallet."""
    from copytrader.clob.client import ClobClient

    client = ClobClient(signed=True)
    info = client.balance_allowance()
    if info is None:
        console.print("[red]could not read balance; check WALLET creds")
        return
    console.print(info)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
