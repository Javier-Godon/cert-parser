"""
Result monad — the core of Railway-Oriented Programming.

A Result[T] is either Success(value: T) or Failure(error: FailureDescription).
Every operation returns Result, never throws. Errors propagate automatically
through the failure track via .flat_map() short-circuiting.

    ┌───────────┐   flat_map    ┌───────────┐   flat_map    ┌──────────┐
    │ validate  │──Success──────│  enrich   │──Success──────│ persist  │──→ Result[T]
    │           │               │           │               │          │
    └─────┬─────┘               └─────┬─────┘               └─────┬────┘
          │ Failure                   │ Failure                   │ Failure
          └───────────────────────────┴───────────────────────────┴──→ Result[T]

Python-specific design choices vs Java:
  - Uses @dataclass instead of sealed interface + record
  - match/case (Python 3.10+) instead of Java 25 pattern matching
  - Generic with TypeVar, not bounded wildcards
  - No need for BiFunction / TriFunction — Python has *args
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    TypeVar,
    Union,
    overload,
)

from railway.failure import ErrorCode, FailureDescription

T = TypeVar("T")
U = TypeVar("U")
A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")
R = TypeVar("R")


class Result(Generic[T]):
    """
    Railway-Oriented Programming Result monad.

    Two possible states:
      - Success(value: T)  — the happy path
      - Failure(error: FailureDescription) — the error track

    All transformations short-circuit on failure, so you only write
    the success path and errors propagate automatically.

    Usage:
        >>> result = Result.success(42).map(lambda x: x * 2)
        >>> result.value()
        84

        >>> result = Result.failure(ErrorCode.VALIDATION_ERROR, "bad input")
        >>> result.map(lambda x: x * 2).is_failure()
        True
    """

    # ──────────────────────── Introspection ────────────────────────

    def is_success(self) -> bool:
        """Check if this Result is a Success."""
        return isinstance(self, Success)

    def is_failure(self) -> bool:
        """Check if this Result is a Failure."""
        return isinstance(self, Failure)

    def value(self) -> T:
        """
        Extract the success value. Raises ValueError if called on a Failure.

        Prefer .either() or match/case for safe access.
        """
        match self:
            case Success(v):
                return v
            case Failure(err):
                raise ValueError(f"Cannot get value from a Failure: {err.message}")
        raise TypeError("unreachable")  # pragma: no cover

    def error(self) -> FailureDescription:
        """
        Extract the failure description. Raises ValueError if called on a Success.

        Prefer .either() or match/case for safe access.
        """
        match self:
            case Failure(err):
                return err
            case Success(v):
                raise ValueError(f"Cannot get error from a Success: {v}")
        raise TypeError("unreachable")  # pragma: no cover

    # ──────────────────────── Core Transformations ────────────────────────

    def either(
        self,
        on_success: Callable[[T], R],
        on_failure: Callable[[FailureDescription], R],
    ) -> R:
        """
        Apply one of two functions depending on the state.

        Mirrors Java's either(). This is the fundamental destructor.

            result.either(
                on_success=lambda user: f"Hello {user.name}",
                on_failure=lambda err: f"Error: {err.message}",
            )
        """
        match self:
            case Success(v):
                return on_success(v)
            case Failure(err):
                return on_failure(err)
        raise TypeError("unreachable")  # pragma: no cover

    def map(self, mapper: Callable[[T], U]) -> Result[U]:
        """
        Transform the success value. Short-circuits on failure.

        Equivalent to Java's .map() or Haskell's fmap.

            Result.success(5).map(lambda x: x * 2)  # → Success(10)
            Result.failure(...).map(lambda x: x * 2)  # → same Failure
        """
        match self:
            case Success(v):
                return Success(mapper(v))
            case Failure(err):
                return Failure(err)
        raise TypeError("unreachable")  # pragma: no cover

    def map_failure(
        self, mapper: Callable[[FailureDescription], FailureDescription]
    ) -> Result[T]:
        """
        Transform the failure description. Passes through success unchanged.

            result.map_failure(lambda err: FailureDescription(err.code, f"Wrapped: {err.message}"))
        """
        match self:
            case Success(_):
                return self
            case Failure(err):
                return Failure(mapper(err))
        raise TypeError("unreachable")  # pragma: no cover

    def flat_map(self, mapper: Callable[[T], Result[U]]) -> Result[U]:
        """
        Chain a Result-returning function. Short-circuits on failure.

        This is the KEY operator of ROP — it connects railway segments.

        Equivalent to Java's .flatMap(), Haskell's >>= (bind), Rust's .and_then().

            def validate(x: int) -> Result[int]:
                if x > 0: return Result.success(x)
                return Result.failure(ErrorCode.VALIDATION_ERROR, "Must be positive")

            Result.success(5).flat_map(validate)   # → Success(5)
            Result.success(-1).flat_map(validate)  # → Failure(...)
        """
        match self:
            case Success(v):
                return mapper(v)
            case Failure(err):
                return Failure(err)
        raise TypeError("unreachable")  # pragma: no cover

    def ensure(
        self,
        predicate: Callable[[T], bool],
        error: FailureDescription | ErrorCode,
        message: str = "",
    ) -> Result[T]:
        """
        Validate the success value against a condition.
        Short-circuits on existing failure.

        Can accept either a FailureDescription or an ErrorCode + message.

            Result.success(order).ensure(
                lambda o: o.total > 0,
                ErrorCode.VALIDATION_ERROR, "Order total must be positive"
            )
        """
        if isinstance(error, ErrorCode):
            error = FailureDescription(code=error, message=message)

        return self.flat_map(
            lambda v: Result.success(v) if predicate(v) else Result.failure_from(error)
        )

    # ──────────────────────── Side Effects ────────────────────────

    def peek(self, action: Callable[[T], Any]) -> Result[T]:
        """
        Execute a side effect on success value without altering the Result.

        Useful for logging, metrics, debugging.

            result.peek(lambda user: logger.info(f"Created user {user.id}"))
        """
        match self:
            case Success(v):
                action(v)
        return self

    def peek_failure(self, action: Callable[[FailureDescription], Any]) -> Result[T]:
        """Execute a side effect on failure without altering the Result."""
        match self:
            case Failure(err):
                action(err)
        return self

    # ──────────────────────── Recovery ────────────────────────

    def recover(self, recovery_fn: Callable[[FailureDescription], T]) -> Result[T]:
        """
        Recover from failure by producing a success value.

            result.recover(lambda err: default_user)
        """
        match self:
            case Success(_):
                return self
            case Failure(err):
                return Success(recovery_fn(err))
        raise TypeError("unreachable")  # pragma: no cover

    def get_or_else(self, default: T) -> T:
        """Extract value or return a default on failure."""
        match self:
            case Success(v):
                return v
            case _:
                return default

    def get_or_else_get(self, fallback: Callable[[FailureDescription], T]) -> T:
        """Extract value or compute a default from the failure."""
        return self.either(lambda v: v, fallback)

    # ──────────────────────── Execution Context ────────────────────────

    def within(self, execution_context: Any) -> Result[T]:
        """
        Execute this Result pipeline within an execution context.

        This is the FP-idiomatic boundary between pure logic and side effects.

        Mirrors Java's .within(txContext) and:
          - Haskell: runIO / runDB
          - F#: computation expressions
          - Elixir: Repo.transaction

            result = (
                Result.success(data)
                .flat_map(validate)
                .flat_map(persist)
                .within(tx_context)
            )
        """
        return execution_context.execute(lambda: self)

    # ──────────────────────── Static Factories ────────────────────────

    @staticmethod
    def success(value: T) -> Result[T]:
        """Create a successful Result wrapping the given value."""
        return Success(value)

    @staticmethod
    def failure_from(error: FailureDescription) -> Result[T]:
        """Create a failed Result from a FailureDescription."""
        return Failure(error)

    @staticmethod
    def failure(
        code: ErrorCode,
        message: str,
        exception: Optional[BaseException] = None,
    ) -> Result[T]:
        """
        Create a failed Result with error code, message, and optional exception.

            Result.failure(ErrorCode.NOT_FOUND, "User not found")
            Result.failure(ErrorCode.DATABASE_ERROR, "Connection failed", ex)
        """
        return Failure(FailureDescription(code=code, message=message, exception=exception))

    # ──────────────────────── Utility Static Factories ────────────────────────

    @staticmethod
    def from_computation(
        computation: Callable[[], T],
        error_code: ErrorCode,
        error_message: str,
    ) -> Result[T]:
        """
        Create a Result from a computation that may raise.

        Wraps exceptions into Result.failure — eliminates try/except boilerplate.

        Before:
            try:
                user = repo.find(user_id)
                return Result.success(user)
            except Exception as e:
                return Result.failure(ErrorCode.DATABASE_ERROR, "Failed", e)

        After:
            return Result.from_computation(
                lambda: repo.find(user_id),
                ErrorCode.DATABASE_ERROR,
                "Failed to find user"
            )
        """
        try:
            return Result.success(computation())
        except Exception as e:
            return Result.failure(error_code, error_message, e)

    @staticmethod
    def from_optional(
        value: Optional[T],
        error_message: str,
        error_code: ErrorCode = ErrorCode.VALIDATION_ERROR,
    ) -> Result[T]:
        """
        Create a Result from an Optional/None value.

        Mirrors Java's fromNullable().

            Result.from_optional(user, "User is required")
            Result.from_optional(config, "Missing config", ErrorCode.CONFIGURATION_ERROR)
        """
        if value is not None:
            return Result.success(value)
        return Result.failure(error_code, error_message)

    @staticmethod
    def combine(
        ra: Result[A],
        rb: Result[B],
        combiner: Callable[[A, B], R],
    ) -> Result[R]:
        """
        Combine two Results. Both must succeed for the combination to succeed.

            order = Result.combine(
                validate_customer(cmd),
                validate_products(cmd),
                lambda customer, products: Order(customer, products),
            )
        """
        return ra.flat_map(lambda a: rb.map(lambda b: combiner(a, b)))

    @staticmethod
    def combine3(
        ra: Result[A],
        rb: Result[B],
        rc: Result[C],
        combiner: Callable[[A, B, C], R],
    ) -> Result[R]:
        """Combine three Results. All must succeed."""
        return ra.flat_map(lambda a: rb.flat_map(lambda b: rc.map(lambda c: combiner(a, b, c))))

    @staticmethod
    def all_of(results: List[Result[T]]) -> Result[List[T]]:
        """
        Collect a list of Results into a Result of list.
        Returns the first failure encountered, or Success with all values.

            results = [validate(item) for item in items]
            all_valid = Result.all_of(results)  # Result[list[Item]]
        """
        values: list[T] = []
        for r in results:
            match r:
                case Success(v):
                    values.append(v)
                case Failure(err):
                    return Failure(err)
        return Success(values)

    # ──────────────────────── Async Support ────────────────────────

    async def map_async(self, mapper: Callable[[T], Awaitable[U]]) -> Result[U]:
        """
        Async map — apply an async function to the success value.

            result = await Result.success(user_id).map_async(fetch_user_from_api)
        """
        match self:
            case Success(v):
                try:
                    mapped = await mapper(v)
                    return Success(mapped)
                except Exception as e:
                    return Failure(
                        FailureDescription(ErrorCode.EXTERNAL_SERVICE_ERROR, "Async operation failed", e)
                    )
            case Failure(err):
                return Failure(err)
        raise TypeError("unreachable")  # pragma: no cover

    async def flat_map_async(self, mapper: Callable[[T], Awaitable[Result[U]]]) -> Result[U]:
        """
        Async flat_map — chain an async Result-returning function.

            result = await Result.success(order).flat_map_async(persist_order)
        """
        match self:
            case Success(v):
                try:
                    return await mapper(v)
                except Exception as e:
                    return Failure(
                        FailureDescription(ErrorCode.EXTERNAL_SERVICE_ERROR, "Async operation failed", e)
                    )
            case Failure(err):
                return Failure(err)
        raise TypeError("unreachable")  # pragma: no cover

    # ──────────────────────── Dunder methods ────────────────────────

    def __bool__(self) -> bool:
        """Allow truthiness check: `if result: ...` succeeds only on Success."""
        return self.is_success()

    def __repr__(self) -> str:
        match self:
            case Success(v):
                return f"Success({v!r})"
            case Failure(err):
                return f"Failure({err.code.value}: {err.message!r})"
        raise TypeError("unreachable")  # pragma: no cover

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Result):
            return NotImplemented
        match (self, other):
            case (Success(a), Success(b)):
                return a == b
            case (Failure(a), Failure(b)):
                return a.code == b.code and a.message == b.message
            case _:
                return False


@dataclass(frozen=True, slots=True)
class Success(Result[T]):
    """The success track — wraps a value of type T."""

    _value: T

    def __init__(self, value: T) -> None:
        if value is None:
            raise TypeError("Success value must not be None")
        object.__setattr__(self, "_value", value)

    # Expose value for match/case: case Success(v)
    def __match_args__(self) -> tuple:  # noqa: N807
        return ("_value",)

    @property
    def _match_value(self) -> T:
        return self._value

    def __repr__(self) -> str:
        return f"Success({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Success):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Success", self._value))


# Enable structural pattern matching: case Success(value)
Success.__match_args__ = ("_value",)


@dataclass(frozen=True, slots=True)
class Failure(Result[T]):
    """The failure track — wraps a FailureDescription."""

    _error: FailureDescription

    def __init__(self, error: FailureDescription) -> None:
        if error is None:
            raise TypeError("Failure error must not be None")
        object.__setattr__(self, "_error", error)

    @property
    def _match_error(self) -> FailureDescription:
        return self._error

    def __repr__(self) -> str:
        return f"Failure({self._error.code.value}: {self._error.message!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Failure):
            return self._error.code == other._error.code and self._error.message == other._error.message
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Failure", self._error.code, self._error.message))


# Enable structural pattern matching: case Failure(error)
Failure.__match_args__ = ("_error",)
