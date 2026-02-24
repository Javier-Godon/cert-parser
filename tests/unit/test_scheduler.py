"""
Unit tests for the scheduler module.

Tests verify scheduler creation, job wiring, startup execution,
and signal handler registration without starting the blocking loop.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apscheduler.triggers.cron import CronTrigger
from railway import ErrorCode
from railway.result import Result

from cert_parser.scheduler import create_scheduler


class TestCreateScheduler:
    """Verify scheduler factory configuration."""

    def test_creates_scheduler_with_job(self) -> None:
        """
        GIVEN a pipeline function
        WHEN create_scheduler is called
        THEN the returned scheduler has exactly one job configured.
        """
        pipeline_fn = MagicMock(return_value=Result.success(5))
        scheduler = create_scheduler(pipeline_fn, cron="0 */12 * * *", run_on_startup=False)

        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "cert_parser_sync"

    def test_uses_cron_trigger(self) -> None:
        """
        GIVEN a cron expression
        WHEN create_scheduler is called
        THEN the job trigger is a CronTrigger (not IntervalTrigger).
        """
        pipeline_fn = MagicMock(return_value=Result.success(5))
        scheduler = create_scheduler(pipeline_fn, cron="0 2 * * *", run_on_startup=False)

        job = scheduler.get_jobs()[0]
        assert isinstance(job.trigger, CronTrigger)

    def test_run_on_startup_executes_pipeline_immediately(self) -> None:
        """
        GIVEN run_on_startup=True
        WHEN create_scheduler is called
        THEN the pipeline function is executed once immediately.
        """
        pipeline_fn = MagicMock(return_value=Result.success(10))
        create_scheduler(pipeline_fn, run_on_startup=True)

        pipeline_fn.assert_called_once()

    def test_run_on_startup_false_does_not_execute(self) -> None:
        """
        GIVEN run_on_startup=False
        WHEN create_scheduler is called
        THEN the pipeline function is NOT executed.
        """
        pipeline_fn = MagicMock(return_value=Result.success(0))
        create_scheduler(pipeline_fn, run_on_startup=False)

        pipeline_fn.assert_not_called()

    def test_startup_handles_pipeline_failure(self) -> None:
        """
        GIVEN a pipeline that returns Failure
        WHEN run_on_startup executes
        THEN the scheduler is still created (no crash).
        """
        pipeline_fn = MagicMock(
            return_value=Result.failure(ErrorCode.EXTERNAL_SERVICE_ERROR, "HTTP 500")
        )
        scheduler = create_scheduler(pipeline_fn, run_on_startup=True)

        pipeline_fn.assert_called_once()
        assert scheduler is not None

    @patch("cert_parser.scheduler.signal.signal")
    def test_registers_signal_handlers(self, mock_signal: MagicMock) -> None:
        """
        GIVEN a pipeline function
        WHEN create_scheduler is called
        THEN SIGINT and SIGTERM handlers are registered.
        """
        import signal

        pipeline_fn = MagicMock(return_value=Result.success(0))
        create_scheduler(pipeline_fn, run_on_startup=False)

        calls = {call.args[0] for call in mock_signal.call_args_list}
        assert signal.SIGINT in calls
        assert signal.SIGTERM in calls
