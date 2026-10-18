from app.application.admin.ports import OutboxEntry
from app.infrastructure.db.models.outbox import OutboxModel
from app.infrastructure.outbox.message import OutboxMessage


def to_model(message: OutboxMessage) -> OutboxModel:
    return OutboxModel(id=message.id, event_type=message.event_type, payload=message.payload)


def to_message(model: OutboxModel) -> OutboxMessage:
    return OutboxMessage(
        id=model.id,
        event_type=model.event_type,
        payload=model.payload,
        created_at=model.created_at,
    )


def to_entry(model: OutboxModel) -> OutboxEntry:
    return OutboxEntry(
        id=model.id,
        event_type=model.event_type,
        payload=model.payload,
        created_at=model.created_at,
        published_at=model.published_at,
    )
