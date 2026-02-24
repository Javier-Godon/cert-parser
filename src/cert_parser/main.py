"""
Application entry point — wires dependencies and starts the scheduler.

Composition root: creates concrete adapters, injects them into the
pipeline, and hands the pipeline to the scheduler.

This is the ONLY place where concrete classes are instantiated.
Everything else depends on Protocol interfaces.

Responsibilities:
  1. Configure structlog for structured JSON logging
  2. Load and validate configuration from environment
  3. Create concrete adapter instances (3 HTTP adapters + parser + repository)
  4. Wire the pipeline (partial application with ports)
  5. Create and start the scheduler
"""

from __future__ import annotations

import logging
import sys
from functools import partial

import structlog

from cert_parser.adapters.cms_parser import CmsMasterListParser
from cert_parser.adapters.http_client import (
    HttpAccessTokenProvider,
    HttpBinaryDownloader,
    HttpSfcTokenProvider,
)
from cert_parser.adapters.repository import PsycopgCertificateRepository
from cert_parser.config import AppSettings
from cert_parser.pipeline import run_pipeline
from cert_parser.scheduler import create_scheduler


def configure_structlog(log_level: str = "INFO") -> None:
    """
    Configure structlog for structured, JSON-formatted logging.

    In production: JSON lines to stdout (machine-readable).
    In development: colored, human-readable console output.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


type _Adapters = tuple[
    HttpAccessTokenProvider,
    HttpSfcTokenProvider,
    HttpBinaryDownloader,
    CmsMasterListParser,
    PsycopgCertificateRepository,
]


def _create_adapters(settings: AppSettings) -> _Adapters:
    """
    Instantiate all concrete adapters from application settings.

    This is the ONLY place where concrete classes are created.
    Creates 5 adapters: access token provider, SFC token provider,
    binary downloader, CMS parser, and PostgreSQL repository.
    """
    access_token_provider = HttpAccessTokenProvider(
        auth_url=settings.auth.url,
        client_id=settings.auth.client_id,
        client_secret=settings.auth.client_secret.get_secret_value(),
        username=settings.auth.username,
        password=settings.auth.password.get_secret_value(),
        timeout=settings.http_timeout_seconds,
    )
    sfc_token_provider = HttpSfcTokenProvider(
        login_url=settings.login.url,
        border_post_id=settings.login.border_post_id,
        box_id=settings.login.box_id,
        passenger_control_type=settings.login.passenger_control_type,
        timeout=settings.http_timeout_seconds,
    )
    downloader = HttpBinaryDownloader(
        download_url=settings.download.url,
        timeout=settings.http_timeout_seconds,
    )
    parser = CmsMasterListParser()
    repository = PsycopgCertificateRepository(
        dsn=settings.database.get_dsn(),
    )
    return access_token_provider, sfc_token_provider, downloader, parser, repository


def main() -> None:
    """Wire dependencies and launch the scheduled pipeline."""
    try:
        settings = AppSettings()
    except Exception as e:
        print(f"FATAL: Configuration error — {e}", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    configure_structlog(settings.log_level)
    log = structlog.get_logger()

    log.info(
        "app.starting",
        version="0.1.0",
        log_level=settings.log_level,
        cron=settings.scheduler.cron,
        run_on_startup=settings.run_on_startup,
    )

    access_token_provider, sfc_token_provider, downloader, parser, repository = (
        _create_adapters(settings)
    )

    pipeline_fn = partial(
        run_pipeline,
        access_token_provider=access_token_provider,
        sfc_token_provider=sfc_token_provider,
        downloader=downloader,
        parser=parser,
        repository=repository,
    )

    scheduler = create_scheduler(
        pipeline_fn=pipeline_fn,
        cron=settings.scheduler.cron,
        run_on_startup=settings.run_on_startup,
    )

    log.info("app.scheduler_starting", cron=settings.scheduler.cron)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("app.shutdown", reason="signal received")
    except SystemExit:
        log.info("app.shutdown", reason="signal received")
        raise
    except Exception as e:
        log.error("app.fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
