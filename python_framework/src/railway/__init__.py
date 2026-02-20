"""
Railway-Oriented Programming (ROP) Framework for Python.

Explicit, composable, functional error handling — no exceptions in business logic.

    from railway import Result, ErrorCode

    def validate_age(age: int) -> Result[int]:
        if age < 0:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Age must be non-negative")
        return Result.success(age)

    result = (
        Result.success({"name": "Alice", "age": 30})
        .flat_map(lambda d: validate_age(d["age"]))
        .map(lambda age: f"Valid user, age {age}")
    )
"""

from railway.result import Result, Success, Failure
from railway.failure import ErrorCode, FailureDescription
from railway.execution import (
    ExecutionContext,
    NoOpExecutionContext,
    LoggingExecutionContext,
    ComposableExecutionContext,
)
from railway.result_failures import ResultFailures
from railway.assertions import ResultAssertions

__all__ = [
    "Result",
    "Success",
    "Failure",
    "ErrorCode",
    "FailureDescription",
    "ExecutionContext",
    "NoOpExecutionContext",
    "LoggingExecutionContext",
    "ComposableExecutionContext",
    "ResultFailures",
    "ResultAssertions",
]

__version__ = "1.0.0"
