"""
FastAPI + Uvicorn ASGI application for Kubernetes deployment.

Runs cert-parser as a web service with health check endpoints and background
scheduler. Uvicorn serves this app with graceful shutdown (SIGTERM → drain + exit).

Architecture:
  - FastAPI: lightweight web framework
  - Uvicorn: production ASGI server (handles signals, graceful shutdown)
  - APScheduler: runs in background thread while Uvicorn listens for /health
  - K8s Probes: liveness (checks scheduler thread alive) + readiness (after first run)

Entry point for production: uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from railway.result import Result

from cert_parser.config import AppSettings
from cert_parser.main import _create_adapters, configure_structlog
from cert_parser.pipeline import run_pipeline
from cert_parser.scheduler import create_scheduler

# ─────────────────────── Global State ───────────────────────
# These are set during app startup and used for health checks.

_scheduler_thread: threading.Thread | None = None
_scheduler_started = False
_scheduler_ready = False  # True after first successful run
_error_message: str | None = None
_pipeline_fn: Callable[[], Result[int]] | None = None
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan context manager — runs on startup and shutdown.

    Startup: Create adapters and start scheduler in background thread.
    Shutdown: Gracefully stop scheduler and thread.
    """
    global _scheduler_thread, _scheduler_started, _error_message

    log.info("asgi.startup", event="lifespan_startup")

    try:
        settings = AppSettings()
    except Exception as e:
        error_msg = f"Configuration error: {e}"
        _error_message = error_msg
        log.error("asgi.startup_error", error=error_msg)
        raise

    configure_structlog(settings.log_level)

    log.info(
        "asgi.startup_config",
        version="0.1.0",
        log_level=settings.log_level,
        interval_hours=settings.scheduler.interval_hours,
        run_on_startup=settings.run_on_startup,
    )

    # Create adapters and pipeline
    try:
        access_token_provider, sfc_token_provider, downloader, parser, repository = (
            _create_adapters(settings)
        )
        from functools import partial

        pipeline_fn = partial(
            run_pipeline,
            access_token_provider=access_token_provider,
            sfc_token_provider=sfc_token_provider,
            downloader=downloader,
            parser=parser,
            repository=repository,
        )

        global _pipeline_fn
        _pipeline_fn = pipeline_fn

        scheduler = create_scheduler(
            pipeline_fn=pipeline_fn,
            interval_hours=settings.scheduler.interval_hours,
            run_on_startup=settings.run_on_startup,
        )
    except Exception as e:
        error_msg = f"Failed to initialize adapters/scheduler: {e}"
        _error_message = error_msg
        log.error("asgi.init_error", error=error_msg)
        raise

    # Start scheduler in background thread
    def run_scheduler() -> None:
        """Run scheduler in background thread (blocking)."""
        global _scheduler_started, _scheduler_ready, _error_message
        try:
            _scheduler_started = True
            log.info("asgi.scheduler_thread_started")
            scheduler.start()
        except KeyboardInterrupt:
            log.info("asgi.scheduler_interrupted")
        except Exception as e:
            error_msg = f"Scheduler error: {e}"
            _error_message = error_msg
            log.error("asgi.scheduler_error", error=error_msg)

    _scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    _scheduler_thread.start()

    # Mark ready after scheduler starts (not after first run, for faster startup)
    await asyncio.sleep(0.1)
    _scheduler_ready = True

    log.info("asgi.startup_complete")

    yield  # ← App is running here; Uvicorn handles requests

    # ──── Shutdown ────
    log.info("asgi.shutdown", reason="SIGTERM or server stop")

    # Gracefully shutdown scheduler
    try:
        scheduler.shutdown(wait=True)
        log.info("asgi.scheduler_shutdown_complete")
    except Exception as e:
        log.warning("asgi.scheduler_shutdown_error", error=str(e))

    # Wait for thread to finish (with timeout)
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5.0)
        if _scheduler_thread.is_alive():
            log.warning("asgi.scheduler_thread_timeout", timeout_seconds=5.0)

    log.info("asgi.shutdown_complete")


# ─────────────────────── FastAPI Application ───────────────────────

app = FastAPI(
    title="cert-parser",
    description="ICAO Master List certificate parser — scheduled batch job as a web service",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> JSONResponse:
    """
    Kubernetes liveness probe — checks if the service is up.

    Returns 200 if:
      - Scheduler thread is alive
      - No fatal errors during startup
    Returns 503 if configuration failed or scheduler crashed.
    """
    if _error_message:
        log.warning("health.check_failed", error=_error_message)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": _error_message},
        )

    if not _scheduler_thread or not _scheduler_thread.is_alive():
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": "scheduler thread not running"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "scheduler_running": True},
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """
    Kubernetes readiness probe — checks if the service is ready to handle requests.

    Returns 202 if:
      - Scheduler started
      - Configuration loaded
      - Scheduler thread is alive
    Returns 503 if not yet ready.

    Note: For a batch job, "ready" means the scheduler is running and the first
    interval timer has started (not necessarily that it has completed a run).
    """
    if not _scheduler_ready or not _scheduler_started:
        return JSONResponse(
            status_code=202,
            content={"status": "starting", "scheduler_started": _scheduler_started},
        )

    if _error_message:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": _error_message},
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "scheduler_running": _scheduler_thread is not None and _scheduler_thread.is_alive(),
        },
    )


@app.get("/info")
async def info() -> dict[str, Any]:
    """
    Info endpoint — returns application metadata.

    Used for debugging and monitoring.
    """
    return {
        "name": "cert-parser",
        "version": "0.1.0",
        "scheduler_running": _scheduler_thread is not None and _scheduler_thread.is_alive(),
        "scheduler_started": _scheduler_started,
        "scheduler_ready": _scheduler_ready,
        "has_error": _error_message is not None,
    }


@app.post("/trigger")
async def trigger() -> JSONResponse:
    """
    Manually trigger the certificate parsing pipeline.

    Intended for testing and debugging — allows triggering the full
    pipeline run from tools like Postman without waiting for the scheduler.

    Runs the pipeline synchronously in a background thread to avoid
    blocking the ASGI event loop.

    Returns 200 with rows_stored on success.
    Returns 500 with error details on pipeline failure.
    Returns 503 if the pipeline is not initialized yet.
    """
    if _pipeline_fn is None:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "reason": "Pipeline not initialized"},
        )

    log.info("trigger.manual_start", source="REST")

    try:
        result = await asyncio.to_thread(_pipeline_fn)
    except Exception as e:
        log.error("trigger.exception", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(e)},
        )

    if result.is_success():
        rows = result.value()
        log.info("trigger.completed", rows_stored=rows)
        return JSONResponse(
            status_code=200,
            content={"status": "success", "rows_stored": rows},
        )

    failure = result.error()
    log.error("trigger.pipeline_failed", failure=str(failure))
    return JSONResponse(
        status_code=500,
        content={
            "status": "failed",
            "error_code": str(failure.code),
            "message": failure.message,
        },
    )


if __name__ == "__main__":
    # For local testing: python -m uvicorn cert_parser.asgi:app --reload
    import uvicorn

    uvicorn.run(
        "cert_parser.asgi:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
