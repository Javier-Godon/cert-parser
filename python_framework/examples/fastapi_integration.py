"""
Example: FastAPI integration with Railway-Oriented Programming.

Shows how Result flows through Controller → Handler → Response
with automatic HTTP status code mapping.

Run:
    pip install railway-rop[fastapi]
    uvicorn examples.fastapi_app:app --reload
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from railway import ErrorCode, Result, NoOpExecutionContext, ResultFailures
from railway.http_support import build_response, HttpStatusMapper, ErrorResponse

# ═══════════════════════════════════════════════════════════════
# This example shows patterns — does NOT require FastAPI installed
# ═══════════════════════════════════════════════════════════════


# --- Domain ---

@dataclass(frozen=True)
class Product:
    id: UUID
    name: str
    price: float


# --- Command & Result ---

@dataclass(frozen=True)
class CreateProductCommand:
    tenant_id: UUID
    name: str
    price: float


@dataclass(frozen=True)
class CreateProductResult:
    product_id: UUID
    name: str
    price: float


# --- Handler ---

class CreateProductHandler:
    def handle(self, command: CreateProductCommand | None) -> Result[CreateProductResult]:
        if command is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Command is mandatory")

        return (
            Result.success(command)
            .ensure(
                lambda c: len(c.name.strip()) >= 2,
                ErrorCode.VALIDATION_ERROR,
                "Product name must be at least 2 characters",
            )
            .ensure(
                lambda c: c.price > 0,
                ErrorCode.VALIDATION_ERROR,
                "Product price must be positive",
            )
            .map(lambda c: CreateProductResult(
                product_id=uuid4(),
                name=c.name,
                price=c.price,
            ))
        )


# --- Controller (framework-agnostic) ---

def create_product_controller(request_body: dict) -> tuple:
    """
    Controller function — would be a FastAPI route handler.

    Shows the pattern:
    1. Parse request
    2. Extract tenant from JWT (simulated)
    3. Call handler
    4. Map Result to HTTP response
    """
    handler = CreateProductHandler()

    # In real code: tenant_id = security_context.get_current_user_context().tenant_id
    tenant_id = uuid4()  # simulated

    command = CreateProductCommand(
        tenant_id=tenant_id,
        name=request_body.get("name", ""),
        price=request_body.get("price", 0),
    )

    result = handler.handle(command)

    # Convert Result → (body, status_code) tuple
    return build_response(result, success_status=201)


# --- Demo ---

def main():
    print("=== FastAPI Integration Pattern Demo ===\n")

    # ✅ Valid request
    body, status = create_product_controller({"name": "Widget", "price": 29.99})
    print(f"1. Status: {status}, Body: {body}")

    # ❌ Invalid name
    body, status = create_product_controller({"name": "X", "price": 29.99})
    print(f"2. Status: {status}, Body: {body}")

    # ❌ Invalid price
    body, status = create_product_controller({"name": "Widget", "price": -5})
    print(f"3. Status: {status}, Body: {body}")

    # Status code mapping demo
    print("\n=== Error Code → HTTP Status Mapping ===")
    for code in ErrorCode:
        print(f"  {code.value:30s} → HTTP {HttpStatusMapper.map_error_code(code)}")


if __name__ == "__main__":
    main()
