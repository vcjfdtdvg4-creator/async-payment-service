from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domain.events import DomainEvent
from app.domain.payments.events import PaymentCreated
from app.domain.payments.values import Currency, Status


@dataclass(slots=True, kw_only=True)
class Payment:
    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str
    idempotency_key: str
    webhook_url: str
    meta: dict[str, Any] = field(default_factory=dict)
    status: Status = Status.pending
    created_at: datetime | None = None
    processed_at: datetime | None = None
    webhook_delivered_at: datetime | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("amount must be positive")

    @classmethod
    def create(
        cls,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        idempotency_key: str,
        webhook_url: str,
        meta: dict[str, Any] | None = None,
    ) -> Payment:
        payment = cls(
            id=uuid.uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
            meta=meta or {},
        )
        payment.events.append(PaymentCreated(payment_id=payment.id))
        return payment

    @property
    def is_final(self) -> bool:
        return self.status in (Status.succeeded, Status.failed)

    @property
    def is_webhook_delivered(self) -> bool:
        return self.webhook_delivered_at is not None

    def matches(
        self,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        webhook_url: str,
        meta: dict[str, Any],
    ) -> bool:
        return (
            self.amount == amount
            and self.currency == currency
            and self.description == description
            and self.webhook_url == webhook_url
            and self.meta == meta
        )

    def pull_events(self) -> list[DomainEvent]:
        events, self.events = self.events, []
        return events
