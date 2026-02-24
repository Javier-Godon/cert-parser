"""
Scheduler — periodic execution of the certificate parsing pipeline.

Infrastructure layer — uses APScheduler (3.x) for lightweight in-process
scheduling driven by a standard 5-field cron expression.

The scheduler wraps pipeline execution within a LoggingExecutionContext
for structured observability (timing, success/failure logging).

Graceful shutdown: handles SIGINT/SIGTERM to stop the scheduler cleanly.
"""

from __future__ import annotations

import signal
import sys
from collections.abc import Callable

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from railway import LoggingExecutionContext
from railway.result import Result

log = structlog.get_logger()


def create_scheduler(
    pipeline_fn: Callable[[], Result[int]],
    cron: str = "0 */6 * * *",
    run_on_startup: bool = True,
) -> BlockingScheduler:
    """
    Create a configured APScheduler that runs the pipeline on a cron schedule.

    Args:
        pipeline_fn: Zero-argument callable returning Result[int] (the wired pipeline).
        cron: Standard 5-field cron expression (minute hour dom month dow).
              Default "0 */6 * * *" runs every 6 hours.
        run_on_startup: If True, execute once immediately before entering the loop.

    Returns:
        A configured BlockingScheduler (call .start() to begin).
    """
    scheduler = BlockingScheduler()
    ctx = LoggingExecutionContext(operation="MasterListSync")

    def _job() -> None:
        """Execute pipeline within logging context and log the outcome."""
        result = ctx.execute(pipeline_fn)
        if result.is_success():
            log.info("scheduler.job_completed", rows_stored=result.value())
        else:
            log.error("scheduler.job_failed", failure=str(result.error()))

    minute, hour, dom, month, dow = cron.split()
    scheduler.add_job(
        _job,
        trigger=CronTrigger(
            minute=minute,
            hour=hour,
            day=dom,
            month=month,
            day_of_week=dow,
        ),
        id="cert_parser_sync",
        name="ICAO Master List sync",
        replace_existing=True,
    )

    if run_on_startup:
        log.info("scheduler.startup_run", message="Running pipeline immediately on startup")
        _job()

    _register_shutdown_signals(scheduler)

    return scheduler


def _register_shutdown_signals(scheduler: BlockingScheduler) -> None:
    """Register SIGINT and SIGTERM handlers for graceful shutdown."""

    def _shutdown(signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        log.info("scheduler.shutdown_requested", signal=sig_name)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
