"""
Execution contexts — separate WHAT (pure logic) from HOW (side effects).

This module implements the execution context pattern from the Java framework,
adapted to Python's Protocol-based structural typing and decorator capabilities.

Core concept (from FP languages):
  - Pure functions describe WHAT should happen → return Result[T]
  - ExecutionContext describes HOW it happens → transactions, logging, caching
  - They are NEVER mixed (no @transactional on stages)

Python equivalents of FP patterns:
  - Haskell: runIO, runST, runDB
  - F#: computation expressions (result { ... }, async { ... })
  - Elixir: Repo.transaction, Task.async

Usage:
    # Define pure pipeline
    def pipeline(cmd: CreateOrderCommand) -> Result[Order]:
        return (
            Result.success(cmd)
            .flat_map(validate)
            .flat_map(enrich)
            .flat_map(persist)
        )

    # Execute within transaction boundary
    result = pipeline(cmd).within(tx_context)

    # Or using decorator
    @with_context(tx_context)
    def handle(cmd: CreateOrderCommand) -> Result[Order]:
        return pipeline(cmd)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from railway.failure import ErrorCode, FailureDescription
from railway.result import Failure, Result

T = TypeVar("T")
logger = logging.getLogger("railway.execution")


# ──────────────────────── Protocol (Interface) ────────────────────────


@runtime_checkable
class ExecutionContext(Protocol):
    """
    Protocol for execution contexts.

    Any class implementing execute(computation) satisfies this protocol
    via Python's structural typing — no explicit inheritance needed.

    This mirrors Java's ExecutionContext interface.
    """

    def execute(self, computation: Callable[[], Result[T]]) -> Result[T]:
        """Execute a Result-returning computation within this context."""
        ...


# ──────────────────────── NoOp (Testing) ────────────────────────


class NoOpExecutionContext:
    """
    Passthrough execution context — runs computation without any wrapper.

    Use for:
      - Unit testing handlers (no real transactions needed)
      - Pure business logic that has no side effects
      - Development/debugging

    Mirrors Java's NoOpExecutionContext and TestExecutionContext.IMMEDIATE.

        handler = CreateOrderHandler(repo, NoOpExecutionContext())
    """

    def execute(self, computation: Callable[[], Result[T]]) -> Result[T]:
        return computation()


# ──────────────────────── Logging ────────────────────────


class LoggingExecutionContext:
    """
    Execution context that logs entry, exit, duration, and result state.

    Wraps another context (decorator pattern) to add observability.

        ctx = LoggingExecutionContext(tx_context, operation="CreateOrder")
    """

    def __init__(
        self,
        inner: ExecutionContext | None = None,
        operation: str = "unknown",
        log_level: int = logging.INFO,
    ) -> None:
        self._inner = inner or NoOpExecutionContext()
        self._operation = operation
        self._log_level = log_level

    def execute(self, computation: Callable[[], Result[T]]) -> Result[T]:
        logger.log(self._log_level, "[%s] Starting execution", self._operation)
        start = time.monotonic()

        try:
            result = self._inner.execute(computation)
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                "[%s] Execution failed after %.3fs: %s",
                self._operation,
                elapsed,
                e,
            )
            return Failure(
                FailureDescription(
                    ErrorCode.TECHNICAL_ERROR,
                    f"Execution failed: {e}",
                    e,
                )
            )

        elapsed = time.monotonic() - start
        state = "SUCCESS" if result.is_success() else "FAILURE"
        logger.log(
            self._log_level,
            "[%s] Completed in %.3fs — %s",
            self._operation,
            elapsed,
            state,
        )
        return result


# ──────────────────────── Composable ────────────────────────


class ComposableExecutionContext:
    """
    Compose multiple execution contexts into a single one.

    Execution order is inside-out (last added runs first around the computation):

        composed = ComposableExecutionContext(
            LoggingExecutionContext(operation="CreateOrder"),
            TransactionContext(session),
        )
        # Logging wraps Transaction wraps computation

    This mirrors Java's ComposableExecutionContext.
    """

    def __init__(self, *contexts: ExecutionContext) -> None:
        if not contexts:
            raise ValueError("At least one execution context is required")
        self._contexts = list(contexts)

    def execute(self, computation: Callable[[], Result[T]]) -> Result[T]:
        # Build the onion: innermost context wraps the computation first
        wrapped = computation
        for ctx in reversed(self._contexts):
            # Capture ctx in closure
            prev = wrapped
            wrapped = lambda _ctx=ctx, _prev=prev: _ctx.execute(_prev)
        return wrapped()


# ──────────────────────── SQLAlchemy Transaction (optional) ────────────────────────


class SQLAlchemyTransactionContext:
    """
    Execution context that wraps computation in a SQLAlchemy transaction.

    Commits on success, rolls back on failure or exception.

    Requires sqlalchemy to be installed (optional dependency).

        from sqlalchemy.orm import Session
        tx_ctx = SQLAlchemyTransactionContext(session)
        result = pipeline(cmd).within(tx_ctx)
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    def execute(self, computation: Callable[[], Result[T]]) -> Result[T]:
        try:
            result = computation()
            if result.is_success():
                self._session.commit()
            else:
                self._session.rollback()
            return result
        except Exception as e:
            self._session.rollback()
            return Failure(
                FailureDescription(
                    ErrorCode.DATABASE_ERROR,
                    f"Transaction failed: {e}",
                    e,
                )
            )


# ──────────────────────── Decorator Helper ────────────────────────


def with_context(ctx: ExecutionContext) -> Callable:
    """
    Decorator to wrap a handler function's result in an execution context.

    Python-idiomatic alternative to .within() chaining:

        @with_context(tx_context)
        def handle(cmd: CreateOrderCommand) -> Result[Order]:
            return (
                Result.success(cmd)
                .flat_map(validate)
                .flat_map(persist)
            )

    Equivalent to:
        def handle(cmd):
            return pipeline(cmd).within(tx_context)
    """

    def decorator(fn: Callable[..., Result[T]]) -> Callable[..., Result[T]]:
        def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
            return ctx.execute(lambda: fn(*args, **kwargs))
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator
