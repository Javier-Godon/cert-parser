"""Tests for ExecutionContext implementations."""

import logging

import pytest

from railway import (
    ErrorCode,
    Result,
    NoOpExecutionContext,
    LoggingExecutionContext,
    ComposableExecutionContext,
)
from railway.execution import SQLAlchemyTransactionContext, with_context


class TestNoOpExecutionContext:
    def test_passthrough(self):
        ctx = NoOpExecutionContext()
        result = ctx.execute(lambda: Result.success(42))
        assert result.value() == 42

    def test_passthrough_failure(self):
        ctx = NoOpExecutionContext()
        result = ctx.execute(lambda: Result.failure(ErrorCode.NOT_FOUND, "gone"))
        assert result.is_failure()


class TestLoggingExecutionContext:
    def test_logs_success(self, caplog):
        ctx = LoggingExecutionContext(operation="TestOp")
        with caplog.at_level(logging.INFO, logger="railway.execution"):
            result = ctx.execute(lambda: Result.success("ok"))
        assert result.value() == "ok"
        assert "TestOp" in caplog.text
        assert "SUCCESS" in caplog.text

    def test_logs_failure(self, caplog):
        ctx = LoggingExecutionContext(operation="TestOp")
        with caplog.at_level(logging.INFO, logger="railway.execution"):
            result = ctx.execute(lambda: Result.failure(ErrorCode.NOT_FOUND, "missing"))
        assert result.is_failure()
        assert "FAILURE" in caplog.text

    def test_catches_exception(self, caplog):
        ctx = LoggingExecutionContext(operation="Boom")
        with caplog.at_level(logging.ERROR, logger="railway.execution"):
            result = ctx.execute(lambda: (_ for _ in ()).throw(RuntimeError("exploded")))
        # The lambda above won't actually work that way, let's use a function
        def failing():
            raise RuntimeError("exploded")
        result = ctx.execute(failing)
        assert result.is_failure()
        assert result.error().code == ErrorCode.TECHNICAL_ERROR

    def test_wraps_inner_context(self):
        inner = NoOpExecutionContext()
        ctx = LoggingExecutionContext(inner=inner, operation="Wrapped")
        result = ctx.execute(lambda: Result.success(99))
        assert result.value() == 99


class TestComposableExecutionContext:
    def test_composes_multiple_contexts(self):
        order: list[str] = []

        class TrackingContext:
            def __init__(self, name: str):
                self.name = name
            def execute(self, computation):
                order.append(f"before-{self.name}")
                result = computation()
                order.append(f"after-{self.name}")
                return result

        composed = ComposableExecutionContext(
            TrackingContext("outer"),
            TrackingContext("inner"),
        )
        result = composed.execute(lambda: Result.success("done"))
        assert result.value() == "done"
        assert order == ["before-outer", "before-inner", "after-inner", "after-outer"]

    def test_requires_at_least_one_context(self):
        with pytest.raises(ValueError, match="(?i)at least one"):
            ComposableExecutionContext()


class TestWithContextDecorator:
    def test_decorator_wraps_function(self):
        ctx = NoOpExecutionContext()

        @with_context(ctx)
        def handle(x: int) -> Result[int]:
            return Result.success(x * 2)

        result = handle(5)
        assert result.value() == 10

    def test_decorator_preserves_name(self):
        ctx = NoOpExecutionContext()

        @with_context(ctx)
        def my_handler(x: int) -> Result[int]:
            """Handler docstring."""
            return Result.success(x)

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "Handler docstring."


class TestWithinMethod:
    def test_result_within_context(self):
        ctx = NoOpExecutionContext()
        result = Result.success(42).within(ctx)
        assert result.value() == 42

    def test_pipeline_within_context(self):
        ctx = NoOpExecutionContext()
        result = (
            Result.success(5)
            .map(lambda x: x * 2)
            .flat_map(lambda x: Result.success(x + 1))
            .within(ctx)
        )
        assert result.value() == 11
