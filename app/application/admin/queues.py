import json
import re
from dataclasses import dataclass
from typing import Any

from app.application.admin.ports import PaymentEventPublisher, QueueAdmin

QUEUE_PREFIX = "payments."
_QUEUE_RE = re.compile(r"^payments\.[A-Za-z0-9._-]+$")


class UnknownQueueError(Exception):
    ...


class RequeueNotAllowedError(Exception):
    ...


def check_queue_name(name: str) -> str:
    if not _QUEUE_RE.match(name):
        raise UnknownQueueError(name)
    return name


@dataclass(frozen=True)
class QueueSnapshot:
    name: str
    info: dict[str, Any]
    messages: list[dict[str, Any]]


class QueueAdminUseCase:
    def __init__(
        self,
        admin: QueueAdmin,
        publisher: PaymentEventPublisher,
        dlq_name: str,
        preview_size: int = 20,
    ) -> None:
        self._admin = admin
        self._publisher = publisher
        self._dlq_name = dlq_name
        self._preview_size = preview_size

    @property
    def dlq_name(self) -> str:
        return self._dlq_name

    async def list_queues(self) -> list[dict[str, Any]]:
        queues = await self._admin.list_queues(QUEUE_PREFIX)
        return sorted(queues, key=lambda q: q["name"])

    async def snapshot(self, name: str) -> QueueSnapshot:
        check_queue_name(name)
        info = await self._admin.get_queue(name)
        messages = await self._admin.peek(name, self._preview_size)
        return QueueSnapshot(name=name, info=info, messages=messages)

    async def requeue(self, name: str, count: int) -> int:
        check_queue_name(name)
        if name != self._dlq_name:
            raise RequeueNotAllowedError(name)
        messages = await self._admin.take(name, count)
        payloads = [_decode_payload(m.get("payload")) for m in messages]
        if payloads:
            await self._publisher.publish_new(payloads, headers={"x-requeued-from": name, "x-attempt": 1})
        return len(payloads)

    async def purge(self, name: str) -> None:
        check_queue_name(name)
        await self._admin.purge(name)


def _decode_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"raw": payload}
    return payload
