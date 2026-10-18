from dataclasses import dataclass
from uuid import UUID

from app.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class PaymentCreated(DomainEvent):
    payment_id: UUID
