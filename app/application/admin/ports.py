"""Порты read-моделей админки (outbox, очереди брокера)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime | None


class OutboxReader(Protocol):
    async def list_recent(self, limit: int) -> list[OutboxEntry]: ...
    async def list_for_payment(self, payment_id: UUID) -> list[OutboxEntry]: ...


class QueueAdmin(Protocol):
    """Чтение и управление очередями брокера (RabbitMQ Management API).

    Очереди и сообщения отдаются в «сыром» виде management API.
    """

    async def list_queues(self, prefix: str) -> list[dict[str, Any]]: ...
    async def get_queue(self, name: str) -> dict[str, Any]: ...
    async def peek(self, name: str, count: int) -> list[dict[str, Any]]: ...
    async def take(self, name: str, count: int) -> list[dict[str, Any]]: ...
    async def purge(self, name: str) -> None: ...


class PaymentEventPublisher(Protocol):
    async def publish_new(self, payloads: list[dict[str, Any]], headers: dict[str, Any]) -> None: ...
