from uuid import uuid4

from pydantic_core import to_jsonable_python

from app.domain.events import DomainEvent
from app.domain.payments.events import PaymentCreated
from app.infrastructure.outbox.message import OutboxMessage

EVENT_TYPES: dict[type[DomainEvent], str] = {
    PaymentCreated: "payment.created",
}


def to_outbox_message(event: DomainEvent) -> OutboxMessage:
    return OutboxMessage(
        id=uuid4(),
        event_type=EVENT_TYPES[type(event)],
        payload=to_jsonable_python(event),
    )
