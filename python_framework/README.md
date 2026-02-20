# Railway-Oriented Programming Framework for Python

> **Explicit, composable, functional error handling — no exceptions in business logic.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Why ROP in Python?

### The Problem

Python's exception-based error handling has fundamental issues for business-critical applications:

```python
# ❌ Traditional Python — hidden control flow
def create_order(request):
    user = get_user(request.user_id)      # May raise UserNotFoundError
    product = get_product(request.sku)     # May raise ProductNotFoundError
    order = Order(user, product)           # May raise ValidationError
    save_order(order)                      # May raise DatabaseError
    send_notification(order)               # May raise EmailError
    return order
```

**Problems:**
1. **Hidden control flow** — any function can throw anything, no indication in the signature
2. **No forced handling** — callers silently ignore potential failures
3. **Try/except pyramid** — nested error handling becomes unreadable
4. **No composability** — can't chain operations that might fail
5. **Exception hierarchy madness** — custom exception classes proliferate

### The Solution — Railway-Oriented Programming

```python
# ✅ ROP — explicit, composable, type-safe
from railway import Result, ErrorCode

def create_order(request) -> Result[Order]:
    return (
        Result.success(request)
        .flat_map(validate_request)        # → Result[ValidRequest]
        .flat_map(find_user)               # → Result[User]
        .flat_map(find_product)            # → Result[Product]
        .flat_map(build_order)             # → Result[Order]
        .flat_map(persist_order)           # → Result[Order]
        .peek(send_notification)           # side effect, doesn't alter result
    )
```

**Benefits:**
1. ✅ **Explicit error channels** — `Result[T]` in every signature
2. ✅ **Forced handling** — you must deal with both tracks
3. ✅ **Flat composition** — no nesting, just `.flat_map()` chains
4. ✅ **Automatic short-circuiting** — failure propagates without boilerplate
5. ✅ **Structured errors** — 13 error codes, not ad-hoc exception trees

---

## Is It Worth It? Java vs Python Comparison

| Aspect | Java (this project) | Python (this framework) |
|--------|-------------------|----------------------|
| **Core need** | CRITICAL — no sum types, checked exceptions are clunky | HIGH — exceptions are invisible and unforced |
| **Type safety** | Sealed interface + generics + JSpecify | `Result[T]` with type hints + mypy strict |
| **Pattern matching** | Java 25 (`case Success(var v)`) | Python 3.10+ (`case Success(v)`) |
| **Boilerplate** | ~600 lines for Result.java | ~350 lines for result.py |
| **Execution context** | Spring TransactionTemplate wrapper | Protocol-based, decorator-friendly |
| **Builder pattern** | Mandatory (Java records are rigid) | Optional (dicts + dataclasses are flexible) |
| **Async** | CompletableFuture + virtual threads | Native async/await |
| **Testing** | Separate assertion classes needed | Same pattern, less ceremony |

**Verdict:** The ROP core (Result monad + execution context) is **equally valuable** in Python. The builder-aggregator pattern is **simpler** in Python. The execution context is **more elegant** with decorators.

---

## Quick Start

### Installation

```bash
# From source (this project)
cd python_framework
pip install -e ".[dev]"

# With FastAPI support
pip install -e ".[fastapi]"

# With Flask support
pip install -e ".[flask]"
```

### 30-Second Example

```python
from railway import Result, ErrorCode

# Define stages as pure functions
def validate_age(age: int) -> Result[int]:
    if age < 0:
        return Result.failure(ErrorCode.VALIDATION_ERROR, "Age must be non-negative")
    if age > 150:
        return Result.failure(ErrorCode.VALIDATION_ERROR, "Age seems unrealistic")
    return Result.success(age)

def validate_name(name: str) -> Result[str]:
    if not name or not name.strip():
        return Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
    return Result.success(name.strip())

# Compose into a pipeline
def create_user(name: str, age: int) -> Result[dict]:
    return (
        Result.combine(
            validate_name(name),
            validate_age(age),
            lambda n, a: {"name": n, "age": a, "id": "user-123"},
        )
    )

# Use it
result = create_user("Alice", 30)
print(result)  # Success({'name': 'Alice', 'age': 30, 'id': 'user-123'})

result = create_user("", -5)
print(result)  # Failure(VALIDATION_ERROR: 'Name is required')
```

---

## API Reference

### `Result[T]` — The Core Monad

#### Creation

```python
# Success
result = Result.success(42)
result = Result.success({"name": "Alice"})

# Failure
result = Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
result = Result.failure(ErrorCode.DATABASE_ERROR, "Connection failed", exception)
result = Result.failure_from(FailureDescription(...))

# From computation (wraps exceptions automatically)
result = Result.from_computation(
    lambda: database.query("SELECT ..."),
    ErrorCode.DATABASE_ERROR,
    "Query failed",
)

# From optional/None
result = Result.from_optional(maybe_value, "Value is required")
```

#### Transformations

```python
# map — transform success value
result.map(lambda x: x * 2)

# flat_map — chain Result-returning functions (THE key operator)
result.flat_map(lambda x: validate(x))

# ensure — conditional validation
result.ensure(lambda x: x > 0, ErrorCode.VALIDATION_ERROR, "Must be positive")

# map_failure — transform error
result.map_failure(lambda e: FailureDescription(e.code, f"Wrapped: {e.message}"))
```

#### Introspection

```python
result.is_success()    # → bool
result.is_failure()    # → bool
result.value()         # → T (raises on Failure)
result.error()         # → FailureDescription (raises on Success)
bool(result)           # → True if Success
```

#### Pattern Matching (Python 3.10+)

```python
from railway import Result, Success, Failure

match result:
    case Success(value):
        print(f"Got: {value}")
    case Failure(error):
        print(f"Error [{error.code.value}]: {error.message}")
```

#### Destructuring

```python
# either — the fundamental destructor
message = result.either(
    on_success=lambda user: f"Hello {user.name}",
    on_failure=lambda err: f"Error: {err.message}",
)
```

#### Side Effects

```python
# peek — execute side effect without altering Result
result.peek(lambda user: logger.info(f"Created: {user.id}"))

# peek_failure — execute side effect on failure
result.peek_failure(lambda err: metrics.increment("failures"))
```

#### Recovery

```python
result.recover(lambda err: default_value)
result.get_or_else(default_value)
result.get_or_else_get(lambda err: compute_fallback(err))
```

#### Combining

```python
# Two results
Result.combine(result_a, result_b, lambda a, b: f"{a}-{b}")

# Three results
Result.combine3(result_a, result_b, result_c, lambda a, b, c: (a, b, c))

# List of results
Result.all_of([result1, result2, result3])  # → Result[list[T]]
```

#### Async

```python
# Async map
result = await Result.success(user_id).map_async(fetch_from_api)

# Async flat_map
result = await Result.success(order).flat_map_async(persist_async)
```

---

### `ErrorCode` — Structured Error Types

```python
from railway import ErrorCode

# Client errors (4xx)
ErrorCode.VALIDATION_ERROR        # 400 — Invalid input
ErrorCode.AUTHENTICATION_ERROR    # 401 — Bad credentials
ErrorCode.AUTHORIZATION_ERROR     # 403 — Insufficient permissions
ErrorCode.NOT_FOUND               # 404 — Resource missing
ErrorCode.BUSINESS_RULE_ERROR     # 409 — Domain constraint violated
ErrorCode.RATE_LIMIT_ERROR        # 429 — Too many requests

# Server errors (5xx)
ErrorCode.TECHNICAL_ERROR         # 500 — Infrastructure issue
ErrorCode.DATABASE_ERROR          # 500 — DB failure
ErrorCode.CONFIGURATION_ERROR     # 500 — Misconfiguration
ErrorCode.EXTERNAL_SERVICE_ERROR  # 502 — External API failure
ErrorCode.SERVICE_UNAVAILABLE_ERROR # 503 — Maintenance
ErrorCode.TIMEOUT_ERROR           # 504 — Timeout
ErrorCode.UNKNOWN_ERROR           # 500 — Unexpected
```

---

### `ExecutionContext` — Separate WHAT from HOW

```python
from railway import NoOpExecutionContext, LoggingExecutionContext, ComposableExecutionContext

# No-op (for testing)
ctx = NoOpExecutionContext()

# Logging
ctx = LoggingExecutionContext(operation="CreateOrder")

# SQLAlchemy transaction
from railway.execution import SQLAlchemyTransactionContext
ctx = SQLAlchemyTransactionContext(db_session)

# Composable (onion layers)
ctx = ComposableExecutionContext(
    LoggingExecutionContext(operation="CreateOrder"),
    SQLAlchemyTransactionContext(db_session),
)

# Usage
result = pipeline(cmd).within(ctx)

# Or as a decorator
from railway.execution import with_context

@with_context(ctx)
def handle(cmd) -> Result[Order]:
    return pipeline(cmd)
```

---

### HTTP Integration

```python
from railway.http_support import build_response, HttpStatusMapper

# Generic (framework-agnostic)
body, status = build_response(result, success_status=201)

# FastAPI
from railway.http_support import build_fastapi_response
return build_fastapi_response(result, success_status=201)

# Flask
from railway.http_support import build_flask_response
return build_flask_response(result, success_status=201)
```

---

### Testing with `ResultAssertions`

```python
from railway import ResultAssertions, ErrorCode

def test_create_user_success():
    result = create_user(valid_command)
    value = ResultAssertions.assert_success(result)
    assert value.name == "Alice"

def test_create_user_validation_error():
    result = create_user(invalid_command)
    error = ResultAssertions.assert_failure(result, ErrorCode.VALIDATION_ERROR)
    ResultAssertions.assert_failure_message_contains(result, "name")

def test_exact_value():
    ResultAssertions.assert_success_value(Result.success(42), 42)
```

---

## Architecture Pattern: Handler → Data/Ports → Stages

The full pattern from the Java project translates directly:

```python
# Data — pure state, NO ports
@dataclass
class CreateOrderData:
    command: CreateOrderCommand
    order: Order | None = None

# Ports — dependencies only
@dataclass(frozen=True)
class CreateOrderPorts:
    repository: OrderRepository

# Stages — pure static methods
class Stages:
    @staticmethod
    def validate(data, ports) -> Result[Data]:     # Impure (uses ports)
        ...

    @staticmethod
    def build_domain(data) -> Result[Data]:         # Pure
        ...

    @staticmethod
    def persist(data, ports) -> Result[Data]:       # Impure
        ...

# Handler — orchestration
class CreateOrderHandler:
    def handle(self, command) -> Result[CreateOrderResult]:
        if command is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Command is mandatory")

        data = CreateOrderData.initialize(command)
        ports = CreateOrderPorts.of(self._repo)

        return (
            Result.success(data)
            .flat_map(lambda d: Stages.validate(d, ports))   # Impure
            .flat_map(Stages.build_domain)                    # Pure
            .flat_map(lambda d: Stages.persist(d, ports))     # Impure
            .flat_map(Stages.build_result)                    # Pure
            .within(self._ctx)
        )
```

See [examples/create_order.py](examples/create_order.py) for a complete working example.

---

## Project Structure

```
python_framework/
├── pyproject.toml              # Package configuration
├── README.md                   # This file
├── src/
│   └── railway/
│       ├── __init__.py         # Public API exports
│       ├── result.py           # Result[T] monad (Success | Failure)
│       ├── failure.py          # ErrorCode enum + FailureDescription
│       ├── execution.py        # ExecutionContext protocol + implementations
│       ├── result_failures.py  # Convenience failure factories
│       ├── assertions.py       # Test assertion helpers
│       └── http_support.py     # HTTP status mapping + response builders
├── tests/
│   ├── test_result.py          # 50+ tests for Result monad
│   ├── test_failure.py         # ErrorCode + FailureDescription tests
│   ├── test_execution.py       # ExecutionContext tests
│   ├── test_result_failures.py # Factory method tests
│   ├── test_assertions.py      # Test helper tests
│   └── test_http_support.py    # HTTP integration tests
└── examples/
    ├── create_order.py         # Full Handler→Data/Ports→Stages example
    ├── fastapi_integration.py  # FastAPI controller pattern
    └── value_objects.py        # Self-validating domain objects
```

---

## Running Tests

```bash
cd python_framework
pip install -e ".[dev]"

# All tests
pytest

# With coverage
pytest --cov=railway --cov-report=term-missing

# Specific test file
pytest tests/test_result.py -v
```

---

## Comparison with Other Python Libraries

| Library | Approach | Difference from railway-rop |
|---------|----------|---------------------------|
| **returns** (dry-python) | Full FP toolkit (Maybe, IO, Reader) | Heavier, academic. railway-rop is focused on business apps. |
| **result** (rustedpy) | Rust-style Result/Option | Minimal. No error codes, no HTTP mapping, no execution context. |
| **polars** / **pydantic** | Validation only | Different scope — they validate data, not orchestrate business logic. |
| **railway-rop** | ROP for business applications | Error codes + execution context + HTTP mapping + test assertions |

---

## License

MIT — same as the parent project.
