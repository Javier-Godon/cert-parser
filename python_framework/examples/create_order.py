"""
Example: Create Order — Full Handler→Data/Ports→Stages pattern in Python.

This mirrors the Java P3 pattern but leverages Python idioms:
  - dataclass instead of Java records
  - Protocol instead of interfaces
  - match/case instead of sealed types
  - Decorator for execution context

Architecture:
    Request → Controller → Handler → within(tx_context) →
      Data.initialize() + Ports.of() →
      validate(Data, Ports) → build_domain(Data) → persist(Data, Ports) → build_result(Data)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from railway import (
    ErrorCode,
    Result,
    NoOpExecutionContext,
    ResultAssertions,
)


# ═══════════════════════════════════════════════════════════════
# Domain — Self-validating value objects & aggregates
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TenantId:
    value: UUID

    @staticmethod
    def create(raw: UUID | str | None) -> Result[TenantId]:
        if raw is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "TenantId is mandatory")
        try:
            return Result.success(TenantId(UUID(str(raw))))
        except (ValueError, AttributeError):
            return Result.failure(ErrorCode.VALIDATION_ERROR, f"Invalid TenantId: {raw}")


@dataclass(frozen=True)
class OrderId:
    value: UUID

    @staticmethod
    def create(raw: UUID | str | None = None) -> Result[OrderId]:
        if raw is None:
            return Result.success(OrderId(uuid4()))
        try:
            return Result.success(OrderId(UUID(str(raw))))
        except ValueError:
            return Result.failure(ErrorCode.VALIDATION_ERROR, f"Invalid OrderId: {raw}")


@dataclass(frozen=True)
class OrderTotal:
    amount: float

    @staticmethod
    def create(amount: float | None) -> Result[OrderTotal]:
        if amount is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Order total is mandatory")
        if amount <= 0:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Order total must be positive")
        return Result.success(OrderTotal(amount))


@dataclass(frozen=True)
class Order:
    """Domain aggregate — TenantId is FIRST field (multi-tenancy)."""
    tenant_id: TenantId
    order_id: OrderId
    total: OrderTotal
    customer_name: str

    @staticmethod
    def create(
        tenant_id: UUID | str,
        total: float,
        customer_name: str,
        order_id: UUID | str | None = None,
    ) -> Result[Order]:
        """Builder-aggregator pattern — sequential validation with fail-fast."""
        return (
            Result.success({})
            .flat_map(lambda b: TenantId.create(tenant_id).map(lambda t: {**b, "tenant_id": t}))
            .flat_map(lambda b: OrderId.create(order_id).map(lambda o: {**b, "order_id": o}))
            .flat_map(lambda b: OrderTotal.create(total).map(lambda t: {**b, "total": t}))
            .flat_map(lambda b: _validate_customer_name(customer_name).map(lambda n: {**b, "name": n}))
            .map(lambda b: Order(
                tenant_id=b["tenant_id"],
                order_id=b["order_id"],
                total=b["total"],
                customer_name=b["name"],
            ))
        )


def _validate_customer_name(name: str | None) -> Result[str]:
    if not name or not name.strip():
        return Result.failure(ErrorCode.VALIDATION_ERROR, "Customer name is mandatory")
    return Result.success(name.strip())


# ═══════════════════════════════════════════════════════════════
# Application Layer — Command, Result, Data, Ports, Stages, Handler
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CreateOrderCommand:
    tenant_id: UUID
    customer_name: str
    total: float


@dataclass(frozen=True)
class CreateOrderResult:
    order_id: UUID
    customer_name: str
    total: float


# --- Data (pure state, NO ports) ---

@dataclass
class CreateOrderData:
    command: CreateOrderCommand
    order: Order | None = None

    @staticmethod
    def initialize(command: CreateOrderCommand) -> CreateOrderData:
        return CreateOrderData(command=command)


# --- Ports (dependencies only) ---

class OrderRepository(Protocol):
    """Port — repository interface (Protocol = structural typing)."""
    def save(self, order: Order) -> Result[Order]: ...
    def exists_for_customer(self, tenant_id: TenantId, customer_name: str) -> Result[bool]: ...


@dataclass(frozen=True)
class CreateOrderPorts:
    repository: OrderRepository

    @staticmethod
    def of(repository: OrderRepository) -> CreateOrderPorts:
        return CreateOrderPorts(repository=repository)


# --- Stages (pure static functions returning Result) ---

class Stages:
    """All business logic as pure static methods."""

    @staticmethod
    def validate_no_duplicate(data: CreateOrderData, ports: CreateOrderPorts) -> Result[CreateOrderData]:
        """IMPURE stage — needs repository."""
        return (
            ports.repository.exists_for_customer(
                TenantId(data.command.tenant_id),
                data.command.customer_name,
            )
            .flat_map(lambda exists:
                Result.failure(ErrorCode.BUSINESS_RULE_ERROR, "Duplicate order for this customer")
                if exists
                else Result.success(data)
            )
        )

    @staticmethod
    def build_domain(data: CreateOrderData) -> Result[CreateOrderData]:
        """PURE stage — builds domain aggregate from command."""
        return Order.create(
            tenant_id=data.command.tenant_id,
            total=data.command.total,
            customer_name=data.command.customer_name,
        ).map(lambda order: _with_order(data, order))

    @staticmethod
    def persist(data: CreateOrderData, ports: CreateOrderPorts) -> Result[CreateOrderData]:
        """IMPURE stage — saves to repository."""
        assert data.order is not None
        return ports.repository.save(data.order).map(lambda saved: _with_order(data, saved))

    @staticmethod
    def build_result(data: CreateOrderData) -> Result[CreateOrderResult]:
        """PURE stage — maps to response."""
        assert data.order is not None
        return Result.success(CreateOrderResult(
            order_id=data.order.order_id.value,
            customer_name=data.order.customer_name,
            total=data.order.total.amount,
        ))


def _with_order(data: CreateOrderData, order: Order) -> CreateOrderData:
    return CreateOrderData(command=data.command, order=order)


# --- Handler (orchestration with explicit port passing) ---

class CreateOrderHandler:
    def __init__(self, repository: OrderRepository, execution_context=None):
        self._repository = repository
        self._ctx = execution_context or NoOpExecutionContext()

    def handle(self, command: CreateOrderCommand | None) -> Result[CreateOrderResult]:
        # FIRST check: null command validation
        if command is None:
            return Result.failure(ErrorCode.VALIDATION_ERROR, "Command is mandatory")

        data = CreateOrderData.initialize(command)
        ports = CreateOrderPorts.of(self._repository)

        return (
            Result.success(data)
            .flat_map(lambda d: Stages.validate_no_duplicate(d, ports))  # Impure
            .flat_map(Stages.build_domain)                                # Pure
            .flat_map(lambda d: Stages.persist(d, ports))                 # Impure
            .flat_map(Stages.build_result)                                # Pure
            .within(self._ctx)
        )


# ═══════════════════════════════════════════════════════════════
# Demo — run this file directly
# ═══════════════════════════════════════════════════════════════


class InMemoryOrderRepository:
    """Simple in-memory implementation for demo/testing."""

    def __init__(self):
        self._orders: dict[UUID, Order] = {}

    def save(self, order: Order) -> Result[Order]:
        self._orders[order.order_id.value] = order
        return Result.success(order)

    def exists_for_customer(self, tenant_id: TenantId, customer_name: str) -> Result[bool]:
        exists = any(
            o.tenant_id == tenant_id and o.customer_name == customer_name
            for o in self._orders.values()
        )
        return Result.success(exists)


def main():
    """Demonstrate the full ROP pipeline."""
    repo = InMemoryOrderRepository()
    handler = CreateOrderHandler(repo)

    tenant = uuid4()

    # ✅ Happy path
    cmd = CreateOrderCommand(tenant_id=tenant, customer_name="Alice", total=150.0)
    result = handler.handle(cmd)
    print(f"1. {result}")  # Success(CreateOrderResult(...))

    # ❌ Duplicate order
    result2 = handler.handle(cmd)
    print(f"2. {result2}")  # Failure(BUSINESS_RULE_ERROR: 'Duplicate order...')

    # ❌ Invalid total
    bad_cmd = CreateOrderCommand(tenant_id=tenant, customer_name="Bob", total=-10.0)
    result3 = handler.handle(bad_cmd)
    print(f"3. {result3}")  # Failure(VALIDATION_ERROR: 'Order total must be positive')

    # ❌ Null command
    result4 = handler.handle(None)
    print(f"4. {result4}")  # Failure(VALIDATION_ERROR: 'Command is mandatory')

    # Pattern matching on result
    from railway.result import Success as S, Failure as F
    print("\n--- Pattern matching ---")
    match result:
        case S(value):
            print(f"✅ Order created: {value.order_id}")
        case F(error):
            print(f"❌ Failed: {error.message}")


if __name__ == "__main__":
    main()
