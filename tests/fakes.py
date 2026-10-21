from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.application.admin.ports import OutboxEntry
from app.domain.events import DomainEvent
from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import DuplicateIdempotencyKeyError
from app.domain.payments.values import Status

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class InMemoryPaymentRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Payment] = {}
        self.seen: list[Payment] = []
        self.race_with: Payment | None = None

    async def add(self, payment: Payment) -> None:
        if self.race_with is not None:
            self.rows[self.race_with.id] = self.race_with
            self.race_with = None
        if any(p.idempotency_key == payment.idempotency_key for p in self.rows.values()):
            raise DuplicateIdempotencyKeyError(payment.idempotency_key)
        payment.created_at = NOW
        self.rows[payment.id] = copy.copy(payment)
        self.seen.append(payment)

    async def get(self, payment_id: UUID) -> Payment | None:
        p = self.rows.get(payment_id)
        return copy.copy(p) if p else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return next((copy.copy(p) for p in self.rows.values() if p.idempotency_key == key), None)

    async def mark_processed(self, payment_id: UUID, status: Status, processed_at: datetime) -> bool:
        p = self.rows[payment_id]
        if p.status != Status.pending:
            return False
        p.status, p.processed_at = status, processed_at
        return True

    async def mark_webhook_delivered(self, payment_id: UUID, delivered_at: datetime) -> None:
        self.rows[payment_id].webhook_delivered_at = delivered_at

    async def list(self, *, status, search, offset, limit) -> list[Payment]:
        return self._filtered(status, search)[offset : offset + limit]

    async def count(self, *, status, search) -> int:
        return len(self._filtered(status, search))

    async def count_by_status(self) -> dict[Status, int]:
        out: dict[Status, int] = {}
        for p in self.rows.values():
            out[p.status] = out.get(p.status, 0) + 1
        return out

    def _filtered(self, status: Status | None, search: str | None) -> list[Payment]:
        items = list(self.rows.values())
        if status is not None:
            items = [p for p in items if p.status == status]
        if search:
            s = search.lower()
            items = [p for p in items if s in p.description.lower() or s in p.idempotency_key.lower()]
        return items


class FakeUnitOfWork:
    def __init__(self, repo: InMemoryPaymentRepository | None = None) -> None:
        self.payments = repo or InMemoryPaymentRepository()
        self.outbox: list[DomainEvent] = []
        self.commits = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.payments.seen = []

    async def commit(self) -> None:
        for p in self.payments.seen:
            self.outbox.extend(p.pull_events())
        self.commits += 1

    async def rollback(self) -> None: ...


class FakeGateway:
    def __init__(self, result: Status = Status.succeeded) -> None:
        self.result = result
        self.calls: list[UUID] = []

    async def charge(self, payment: Payment) -> Status:
        self.calls.append(payment.id)
        return self.result


class FakeNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[Payment] = []

    async def notify(self, payment: Payment) -> None:
        if self.fail:
            raise ConnectionError("webhook is down")
        self.sent.append(payment)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeOutboxReader:
    def __init__(self, entries: list[OutboxEntry] | None = None) -> None:
        self.entries = entries or []

    async def list_recent(self, limit: int) -> list[OutboxEntry]:
        return self.entries[:limit]

    async def list_for_payment(self, payment_id: UUID) -> list[OutboxEntry]:
        return [e for e in self.entries if e.payload.get("payment_id") == str(payment_id)]


class FakeQueueAdmin:
    def __init__(self, queues: dict[str, list[dict[str, Any]]]) -> None:
        self.queues = queues

    async def list_queues(self, prefix: str) -> list[dict[str, Any]]:
        return [{"name": n, "messages": len(m)} for n, m in self.queues.items() if n.startswith(prefix)]

    async def get_queue(self, name: str) -> dict[str, Any]:
        return {"name": name, "messages": len(self.queues[name])}

    async def peek(self, name: str, count: int) -> list[dict[str, Any]]:
        return self.queues[name][:count]

    async def take(self, name: str, count: int) -> list[dict[str, Any]]:
        taken, self.queues[name] = self.queues[name][:count], self.queues[name][count:]
        return taken

    async def purge(self, name: str) -> None:
        self.queues[name] = []


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def publish_new(self, payloads: list[dict[str, Any]], headers: dict[str, Any]) -> None:
        self.published.extend((p, headers) for p in payloads)
