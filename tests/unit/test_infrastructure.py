import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.domain.payments.values import Status
from app.infrastructure.broker.retry import RetryPublisher, attempt_from_headers
from app.infrastructure.broker.topology import retry_queues
from app.infrastructure.mappers.payment import to_entity, to_model
from app.infrastructure.outbox.serializer import to_outbox_message
from app.infrastructure.webhooks.client import HttpWebhookNotifier
from app.infrastructure.webhooks.payload import build_webhook_payload


@pytest.mark.parametrize(
    ("headers", "expected"),
    [(None, 1), ({}, 1), ({"x-attempt": 2}, 2), ({"x-attempt": "3"}, 3), ({"x-attempt": "junk"}, 1), ({"x-attempt": 0}, 1)],
)
def test_attempt_from_headers(headers, expected):
    assert attempt_from_headers(headers) == expected


def test_retry_queues_have_growing_ttl():
    queues = retry_queues()
    assert [q.name for q in queues] == ["payments.new.retry.1", "payments.new.retry.2"]
    assert [q.arguments["x-message-ttl"] for q in queues] == [5000, 10000]


class _RecordingBroker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def publish(self, body, **kwargs) -> None:
        self.calls.append({"body": body, **kwargs})


async def test_reroute_to_retry_then_dlq():
    broker = _RecordingBroker()
    retry = RetryPublisher(broker, max_attempts=3)
    body = {"payment_id": "x"}

    await retry.reroute(body, 1, RuntimeError("boom"))
    await retry.reroute(body, 3, RuntimeError("boom"))

    first, last = broker.calls
    assert first["queue"] == "payments.new.retry.1" and first["headers"]["x-attempt"] == 2
    assert last["queue"] == "payments.dlq" and last["headers"]["x-attempt"] == 3
    assert "boom" in last["headers"]["x-last-error"]


def test_mapper_roundtrip(make_payment):
    p = make_payment()
    p.created_at = datetime.now(timezone.utc)
    model = to_model(p)
    model.created_at = p.created_at
    back = to_entity(model)
    assert (back.id, back.amount, back.currency, back.status, back.meta) == (p.id, p.amount, p.currency, p.status, p.meta)


def test_outbox_message_payload_matches_consumer_contract(make_payment):
    p = make_payment()
    (event,) = p.pull_events()
    msg = to_outbox_message(event)
    assert msg.event_type == "payment.created"
    assert msg.payload == {"payment_id": str(p.id)}


async def test_webhook_notifier_posts_payload_and_raises_on_error(make_payment):
    p = make_payment()
    p.status = Status.succeeded
    p.created_at = datetime.now(timezone.utc)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200 if len(seen) == 1 else 500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = HttpWebhookNotifier(client)
        await notifier.notify(p)
        with pytest.raises(httpx.HTTPStatusError):
            await notifier.notify(p)

    assert seen[0].headers["X-Payment-Event"] == "payment.processed"
    payload = build_webhook_payload(p)
    assert payload["status"] == "succeeded" and payload["payment_id"] == str(p.id)
    assert uuid.UUID(payload["payment_id"]) == p.id
