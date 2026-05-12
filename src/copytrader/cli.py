"""Tiny CLI for operator convenience.

Only used for ad-hoc ops (mostly browser-completable now). Commands defer
to worker job-queue when possible (no duplicate execution paths).
"""
from __future__ import annotations

import json

import click

from copytrader.logging_setup import setup_logging


@click.group()
def main() -> None:
    setup_logging()


@main.command()
def healthcheck() -> None:
    """Print DB ping result."""
    from copytrader.db.engine import ping
    click.echo(json.dumps({"db": "ok" if ping() else "down"}))


@main.command()
@click.option("--window", type=int, default=30)
def phase0(window: int) -> None:
    """Enqueue a phase0 job. Does NOT execute it (the worker does)."""
    from copytrader.jobs.queue import enqueue
    job_id = enqueue("phase0", {"window": window})
    click.echo(json.dumps({"job_id": job_id, "kind": "phase0", "window": window}))


if __name__ == "__main__":
    main()
