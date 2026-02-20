"""
Comprehensive tests for Result monad — mirrors Java's ResultUtilitiesTest.

Tests cover:
  - Success/Failure creation and introspection
  - map, flat_map, ensure transformations
  - Side effects (peek, peek_failure)
  - Recovery (recover, get_or_else, get_or_else_get)
  - Static factories (from_computation, from_optional, combine, all_of)
  - Pattern matching (match/case)
  - Equality and repr
  - Async operations
"""

from __future__ import annotations

import asyncio

import pytest

from railway import ErrorCode, FailureDescription, Result, Success, Failure


# ═══════════════════════════════════════════════════════════════
# 1. Creation & Introspection
# ═══════════════════════════════════════════════════════════════


class TestSuccessCreation:
    def test_success_wraps_value(self):
        result = Result.success(42)
        assert result.is_success()
        assert not result.is_failure()
        assert result.value() == 42

    def test_success_with_string(self):
        result = Result.success("hello")
        assert result.value() == "hello"

    def test_success_with_complex_object(self):
        data = {"name": "Alice", "age": 30}
        result = Result.success(data)
        assert result.value() == data

    def test_success_rejects_none(self):
        with pytest.raises(TypeError, match="must not be None"):
            Success(None)

    def test_success_is_truthy(self):
        assert Result.success(42)
        assert bool(Result.success("x"))


class TestFailureCreation:
    def test_failure_with_code_and_message(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
        assert result.is_failure()
        assert not result.is_success()
        assert result.error().code == ErrorCode.VALIDATION_ERROR
        assert result.error().message == "Name is required"

    def test_failure_with_exception(self):
        ex = ValueError("bad value")
        result = Result.failure(ErrorCode.DATABASE_ERROR, "Query failed", ex)
        assert result.error().exception is ex

    def test_failure_from_description(self):
        desc = FailureDescription(ErrorCode.NOT_FOUND, "User not found")
        result = Result.failure_from(desc)
        assert result.error() == desc

    def test_failure_rejects_none(self):
        with pytest.raises(TypeError, match="must not be None"):
            Failure(None)

    def test_failure_is_falsy(self):
        assert not Result.failure(ErrorCode.VALIDATION_ERROR, "bad")


class TestValueExtraction:
    def test_value_on_failure_raises(self):
        result = Result.failure(ErrorCode.NOT_FOUND, "missing")
        with pytest.raises(ValueError, match="Cannot get value from a Failure"):
            result.value()

    def test_error_on_success_raises(self):
        result = Result.success(42)
        with pytest.raises(ValueError, match="Cannot get error from a Success"):
            result.error()


# ═══════════════════════════════════════════════════════════════
# 2. Transformations
# ═══════════════════════════════════════════════════════════════


class TestMap:
    def test_map_transforms_success_value(self):
        result = Result.success(5).map(lambda x: x * 2)
        assert result.value() == 10

    def test_map_short_circuits_on_failure(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "bad").map(lambda x: x * 2)
        assert result.is_failure()
        assert result.error().code == ErrorCode.VALIDATION_ERROR

    def test_map_chain(self):
        result = (
            Result.success(3)
            .map(lambda x: x + 1)
            .map(lambda x: x * 2)
            .map(str)
        )
        assert result.value() == "8"


class TestMapFailure:
    def test_map_failure_transforms_error(self):
        result = (
            Result.failure(ErrorCode.VALIDATION_ERROR, "original")
            .map_failure(lambda e: FailureDescription(e.code, f"Wrapped: {e.message}"))
        )
        assert result.error().message == "Wrapped: original"

    def test_map_failure_passes_through_success(self):
        result = Result.success(42).map_failure(
            lambda e: FailureDescription(e.code, "should not run")
        )
        assert result.value() == 42


class TestFlatMap:
    def test_flat_map_chains_success(self):
        def double_if_positive(x: int) -> Result[int]:
            if x > 0:
                return Result.success(x * 2)
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Must be positive")

        result = Result.success(5).flat_map(double_if_positive)
        assert result.value() == 10

    def test_flat_map_short_circuits_on_first_failure(self):
        calls: list[str] = []

        def step_a(x: int) -> Result[int]:
            calls.append("a")
            return Result.failure(ErrorCode.VALIDATION_ERROR, "fail at a")

        def step_b(x: int) -> Result[int]:
            calls.append("b")
            return Result.success(x + 1)

        result = Result.success(1).flat_map(step_a).flat_map(step_b)
        assert result.is_failure()
        assert calls == ["a"]  # step_b never called

    def test_flat_map_pipeline(self):
        """Full railway pipeline — the core pattern."""
        def validate(order: dict) -> Result[dict]:
            if order.get("total", 0) <= 0:
                return Result.failure(ErrorCode.VALIDATION_ERROR, "Total must be positive")
            return Result.success(order)

        def enrich(order: dict) -> Result[dict]:
            return Result.success({**order, "status": "enriched"})

        def persist(order: dict) -> Result[str]:
            return Result.success(f"ORDER-{order['id']}")

        result = (
            Result.success({"id": 1, "total": 100})
            .flat_map(validate)
            .flat_map(enrich)
            .flat_map(persist)
        )
        assert result.value() == "ORDER-1"


class TestEnsure:
    def test_ensure_passes_when_predicate_true(self):
        result = Result.success(10).ensure(
            lambda x: x > 0,
            ErrorCode.VALIDATION_ERROR,
            "Must be positive",
        )
        assert result.value() == 10

    def test_ensure_fails_when_predicate_false(self):
        result = Result.success(-1).ensure(
            lambda x: x > 0,
            ErrorCode.VALIDATION_ERROR,
            "Must be positive",
        )
        assert result.is_failure()
        assert result.error().message == "Must be positive"

    def test_ensure_with_failure_description(self):
        error = FailureDescription(ErrorCode.BUSINESS_RULE_ERROR, "Too expensive")
        result = Result.success(1000).ensure(lambda x: x < 500, error)
        assert result.error().code == ErrorCode.BUSINESS_RULE_ERROR

    def test_ensure_short_circuits_on_existing_failure(self):
        result = (
            Result.failure(ErrorCode.NOT_FOUND, "missing")
            .ensure(lambda x: True, ErrorCode.VALIDATION_ERROR, "never reached")
        )
        assert result.error().code == ErrorCode.NOT_FOUND

    def test_ensure_chain(self):
        result = (
            Result.success(50)
            .ensure(lambda x: x > 0, ErrorCode.VALIDATION_ERROR, "positive")
            .ensure(lambda x: x < 100, ErrorCode.VALIDATION_ERROR, "under 100")
            .ensure(lambda x: x % 2 == 0, ErrorCode.VALIDATION_ERROR, "even")
        )
        assert result.value() == 50


# ═══════════════════════════════════════════════════════════════
# 3. Either / Pattern Matching
# ═══════════════════════════════════════════════════════════════


class TestEither:
    def test_either_on_success(self):
        msg = Result.success("Alice").either(
            on_success=lambda name: f"Hello, {name}!",
            on_failure=lambda err: f"Error: {err.message}",
        )
        assert msg == "Hello, Alice!"

    def test_either_on_failure(self):
        msg = Result.failure(ErrorCode.NOT_FOUND, "not found").either(
            on_success=lambda v: f"Got: {v}",
            on_failure=lambda err: f"Error: {err.message}",
        )
        assert msg == "Error: not found"


class TestPatternMatching:
    """Python 3.10+ match/case — the native alternative to Java's sealed interface."""

    def test_match_success(self):
        result = Result.success(42)
        match result:
            case Success(v):
                assert v == 42
            case Failure(_):
                pytest.fail("Should be Success")

    def test_match_failure(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "bad")
        match result:
            case Success(_):
                pytest.fail("Should be Failure")
            case Failure(err):
                assert err.code == ErrorCode.VALIDATION_ERROR

    def test_match_in_function(self):
        def describe(result: Result[int]) -> str:
            match result:
                case Success(v):
                    return f"Got {v}"
                case Failure(err):
                    return f"Failed: {err.message}"
            return "unreachable"

        assert describe(Result.success(7)) == "Got 7"
        assert describe(Result.failure(ErrorCode.NOT_FOUND, "nope")) == "Failed: nope"


# ═══════════════════════════════════════════════════════════════
# 4. Side Effects
# ═══════════════════════════════════════════════════════════════


class TestPeek:
    def test_peek_executes_on_success(self):
        captured: list[int] = []
        result = Result.success(42).peek(lambda v: captured.append(v))
        assert captured == [42]
        assert result.value() == 42

    def test_peek_skips_on_failure(self):
        captured: list[int] = []
        Result.failure(ErrorCode.NOT_FOUND, "nope").peek(lambda v: captured.append(v))
        assert captured == []

    def test_peek_failure_executes_on_failure(self):
        captured: list[str] = []
        Result.failure(ErrorCode.NOT_FOUND, "gone").peek_failure(
            lambda err: captured.append(err.message)
        )
        assert captured == ["gone"]

    def test_peek_failure_skips_on_success(self):
        captured: list[str] = []
        Result.success(42).peek_failure(lambda err: captured.append(err.message))
        assert captured == []


# ═══════════════════════════════════════════════════════════════
# 5. Recovery
# ═══════════════════════════════════════════════════════════════


class TestRecovery:
    def test_recover_from_failure(self):
        result = Result.failure(ErrorCode.NOT_FOUND, "missing").recover(lambda err: "default")
        assert result.value() == "default"

    def test_recover_passes_through_success(self):
        result = Result.success(42).recover(lambda err: 0)
        assert result.value() == 42

    def test_get_or_else_on_failure(self):
        value = Result.failure(ErrorCode.NOT_FOUND, "x").get_or_else("fallback")
        assert value == "fallback"

    def test_get_or_else_on_success(self):
        value = Result.success("actual").get_or_else("fallback")
        assert value == "actual"

    def test_get_or_else_get(self):
        value = Result.failure(ErrorCode.NOT_FOUND, "x").get_or_else_get(
            lambda err: f"recovered from {err.code.value}"
        )
        assert value == "recovered from NOT_FOUND"


# ═══════════════════════════════════════════════════════════════
# 6. Static Factories
# ═══════════════════════════════════════════════════════════════


class TestFromComputation:
    def test_success_when_no_exception(self):
        result = Result.from_computation(
            lambda: 42,
            ErrorCode.DATABASE_ERROR,
            "query failed",
        )
        assert result.value() == 42

    def test_failure_when_exception_raised(self):
        result = Result.from_computation(
            lambda: 1 / 0,
            ErrorCode.DATABASE_ERROR,
            "division error",
        )
        assert result.is_failure()
        assert result.error().code == ErrorCode.DATABASE_ERROR
        assert isinstance(result.error().exception, ZeroDivisionError)


class TestFromOptional:
    def test_success_when_value_present(self):
        result = Result.from_optional("hello", "value required")
        assert result.value() == "hello"

    def test_failure_when_none(self):
        result = Result.from_optional(None, "value required")
        assert result.is_failure()
        assert result.error().code == ErrorCode.VALIDATION_ERROR

    def test_custom_error_code(self):
        result = Result.from_optional(None, "config missing", ErrorCode.CONFIGURATION_ERROR)
        assert result.error().code == ErrorCode.CONFIGURATION_ERROR


class TestCombine:
    def test_combine_two_successes(self):
        result = Result.combine(
            Result.success("Alice"),
            Result.success(30),
            lambda name, age: f"{name} is {age}",
        )
        assert result.value() == "Alice is 30"

    def test_combine_first_fails(self):
        result = Result.combine(
            Result.failure(ErrorCode.VALIDATION_ERROR, "bad name"),
            Result.success(30),
            lambda name, age: f"{name} is {age}",
        )
        assert result.error().message == "bad name"

    def test_combine_second_fails(self):
        result = Result.combine(
            Result.success("Alice"),
            Result.failure(ErrorCode.VALIDATION_ERROR, "bad age"),
            lambda name, age: f"{name} is {age}",
        )
        assert result.error().message == "bad age"

    def test_combine_three(self):
        result = Result.combine3(
            Result.success("a"),
            Result.success("b"),
            Result.success("c"),
            lambda a, b, c: f"{a}-{b}-{c}",
        )
        assert result.value() == "a-b-c"


class TestAllOf:
    def test_all_successes(self):
        results = [Result.success(i) for i in range(5)]
        combined = Result.all_of(results)
        assert combined.value() == [0, 1, 2, 3, 4]

    def test_first_failure_wins(self):
        results = [
            Result.success(1),
            Result.failure(ErrorCode.VALIDATION_ERROR, "second fails"),
            Result.success(3),
        ]
        combined = Result.all_of(results)
        assert combined.error().message == "second fails"

    def test_empty_list(self):
        combined = Result.all_of([])
        assert combined.value() == []


# ═══════════════════════════════════════════════════════════════
# 7. Equality & Repr
# ═══════════════════════════════════════════════════════════════


class TestEqualityAndRepr:
    def test_success_equality(self):
        assert Result.success(42) == Result.success(42)
        assert Result.success(42) != Result.success(99)

    def test_failure_equality(self):
        a = Result.failure(ErrorCode.NOT_FOUND, "x")
        b = Result.failure(ErrorCode.NOT_FOUND, "x")
        c = Result.failure(ErrorCode.NOT_FOUND, "y")
        assert a == b
        assert a != c

    def test_success_not_equal_to_failure(self):
        assert Result.success(42) != Result.failure(ErrorCode.NOT_FOUND, "x")

    def test_repr_success(self):
        assert "Success(42)" in repr(Result.success(42))

    def test_repr_failure(self):
        r = repr(Result.failure(ErrorCode.NOT_FOUND, "gone"))
        assert "NOT_FOUND" in r
        assert "gone" in r


# ═══════════════════════════════════════════════════════════════
# 8. Async Operations
# ═══════════════════════════════════════════════════════════════


class TestAsync:
    @pytest.mark.asyncio
    async def test_map_async_success(self):
        async def double(x: int) -> int:
            return x * 2

        result = await Result.success(5).map_async(double)
        assert result.value() == 10

    @pytest.mark.asyncio
    async def test_map_async_failure_passthrough(self):
        async def double(x: int) -> int:
            return x * 2

        result = await Result.failure(ErrorCode.NOT_FOUND, "x").map_async(double)
        assert result.is_failure()

    @pytest.mark.asyncio
    async def test_flat_map_async_success(self):
        async def validate(x: int) -> Result[int]:
            if x > 0:
                return Result.success(x)
            return Result.failure(ErrorCode.VALIDATION_ERROR, "negative")

        result = await Result.success(5).flat_map_async(validate)
        assert result.value() == 5

    @pytest.mark.asyncio
    async def test_flat_map_async_catches_exception(self):
        async def failing(x: int) -> Result[int]:
            raise RuntimeError("boom")

        result = await Result.success(5).flat_map_async(failing)
        assert result.is_failure()
        assert result.error().code == ErrorCode.EXTERNAL_SERVICE_ERROR
