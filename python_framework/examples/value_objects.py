"""
Example: Value Object validation using ROP.

Shows how Python dataclasses + Result.create() patterns replace
Java's builder-aggregator pattern for self-validating domain objects.

Key differences from Java:
  - No need for sealed interfaces — dataclass(frozen=True) is enough
  - match/case replaces Java's pattern matching
  - Less boilerplate thanks to dynamic typing + protocols
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from railway import ErrorCode, Result


# ═══════════════════════════════════════════════════════════════
# Value Objects — self-validating via factory methods
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Email:
    """Self-validating email value object."""
    value: str

    @staticmethod
    def create(raw: str | None) -> Result[Email]:
        if not raw or not raw.strip():
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Email is mandatory")
        normalized = raw.strip().lower()
        if "@" not in normalized or "." not in normalized.split("@")[-1]:
            return Result.failure(ErrorCode.VALIDATION_ERROR, f"Invalid email format: {raw}")
        if len(normalized) > 255:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Email must not exceed 255 characters")
        return Result.success(Email(normalized))


@dataclass(frozen=True)
class PersonName:
    """Self-validating person name value object."""
    first_name: str
    last_name: str

    @staticmethod
    def create(first: str | None, last: str | None) -> Result[PersonName]:
        if not first or not first.strip():
            return Result.failure(ErrorCode.VALIDATION_ERROR, "First name is mandatory")
        if not last or not last.strip():
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Last name is mandatory")
        if len(first) > 100:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "First name must not exceed 100 characters")
        if len(last) > 100:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Last name must not exceed 100 characters")
        return Result.success(PersonName(first.strip(), last.strip()))


@dataclass(frozen=True)
class Price:
    """Self-validating price value object with currency."""
    amount: float
    currency: str

    VALID_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF"}

    @staticmethod
    def create(amount: float | None, currency: str | None = "EUR") -> Result[Price]:
        if amount is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Price amount is mandatory")
        if amount < 0:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Price amount must be non-negative")
        if currency is None or currency.upper() not in Price.VALID_CURRENCIES:
            return Result.failure(
                ErrorCode.VALIDATION_ERROR,
                f"Invalid currency: {currency}. Valid: {', '.join(sorted(Price.VALID_CURRENCIES))}",
            )
        return Result.success(Price(round(amount, 2), currency.upper()))


# ═══════════════════════════════════════════════════════════════
# Domain Aggregate — builder-aggregator pattern in Python
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Customer:
    """
    Domain aggregate with TenantId as FIRST field.

    Uses builder-aggregator pattern: sequential validation with fail-fast.
    Each step validates one field and accumulates into a builder dict.
    """
    tenant_id: UUID
    customer_id: UUID
    name: PersonName
    email: Email
    price_tier: Price

    @staticmethod
    def create(
        tenant_id: UUID | str | None,
        first_name: str | None,
        last_name: str | None,
        email: str | None,
        price_amount: float | None = 0.0,
        price_currency: str | None = "EUR",
        customer_id: UUID | None = None,
    ) -> Result[Customer]:
        """
        Builder-aggregator: validates each field sequentially.

        This is the Python equivalent of Java's:
            Result.success(Builder.builder().build())
                .flatMap(b -> TenantId.create(x).map(b::withTenantId))
                .flatMap(b -> Email.create(x).map(b::withEmail))
                ...
        """
        b: dict = {}  # Builder accumulator

        return (
            Result.success(b)
            # Validate tenant_id
            .flat_map(lambda b: (
                Result.failure(ErrorCode.VALIDATION_ERROR, "TenantId is mandatory")
                if tenant_id is None
                else Result.success({**b, "tenant_id": UUID(str(tenant_id))})
            ))
            # Validate customer_id (auto-generate if not provided)
            .map(lambda b: {**b, "customer_id": customer_id or uuid4()})
            # Validate name
            .flat_map(lambda b: PersonName.create(first_name, last_name).map(
                lambda name: {**b, "name": name}
            ))
            # Validate email
            .flat_map(lambda b: Email.create(email).map(
                lambda e: {**b, "email": e}
            ))
            # Validate price tier
            .flat_map(lambda b: Price.create(price_amount, price_currency).map(
                lambda p: {**b, "price_tier": p}
            ))
            # Build the aggregate
            .map(lambda b: Customer(
                tenant_id=b["tenant_id"],
                customer_id=b["customer_id"],
                name=b["name"],
                email=b["email"],
                price_tier=b["price_tier"],
            ))
        )


# ═══════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════


def main():
    tenant = uuid4()

    print("=== Value Object Validation with ROP ===\n")

    # ✅ Valid customer
    result = Customer.create(
        tenant_id=tenant,
        first_name="Alice",
        last_name="Smith",
        email="alice@example.com",
        price_amount=99.99,
    )
    print(f"1. Valid:   {result}")

    # ❌ Missing email
    result2 = Customer.create(
        tenant_id=tenant,
        first_name="Bob",
        last_name="Jones",
        email=None,
    )
    print(f"2. No email: {result2}")

    # ❌ Invalid email format
    result3 = Customer.create(
        tenant_id=tenant,
        first_name="Carol",
        last_name="White",
        email="not-an-email",
    )
    print(f"3. Bad email: {result3}")

    # ❌ Missing tenant
    result4 = Customer.create(
        tenant_id=None,
        first_name="Dave",
        last_name="Brown",
        email="dave@example.com",
    )
    print(f"4. No tenant: {result4}")

    # ❌ Negative price
    result5 = Customer.create(
        tenant_id=tenant,
        first_name="Eve",
        last_name="Green",
        email="eve@example.com",
        price_amount=-10.0,
    )
    print(f"5. Neg price: {result5}")

    # Pattern matching
    print("\n=== Pattern Matching ===")
    from railway.result import Success, Failure
    match result:
        case Success(customer):
            print(f"✅ Created: {customer.name.first_name} {customer.name.last_name} ({customer.email.value})")
        case Failure(error):
            print(f"❌ Failed: [{error.code.value}] {error.message}")


if __name__ == "__main__":
    main()
