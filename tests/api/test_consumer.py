import uuid

import httpx
import pytest
from fast_depends import dependency_provider
from faststream.rabbit import TestRabbitBroker

from app.application.payments.process_payment import ProcessPaymentUseCase
from app.domain.payments.values import Status
from app.infrastructure.broker.connection import broker
from app.infrastructure.broker.retry import RetryPublisher
from app.infrastructure.broker.topology import new_queue, payments_exchange
from app.presentation.consumer import deps
from app.presentation.consumer.handlers.payments import handle_payment_created, router
from tests.fakes import FakeGateway, FakeNotifier, FakeUnitOfWork, FixedClock

broker.include_router(router)


class _RecordingRetry(RetryPublisher):
    def __init__(self) -> None:
        self.calls: list[tuple[dict, int, str]] = []

    async def reroute(self, body, attempt, exc) -> None:
        self.calls.append((body, attempt, repr(exc)))


class _State:
    """FastStream строит граф зависимостей один раз, поэтому фейки подменяем через общий holder."""

    uow: FakeUnitOfWork
    notifier: FakeNotifier
    retry: _RecordingRetry


_state = _State()
dependency_provider.override(
    deps.get_process_payment_use_case,
    lambda **_: ProcessPaymentUseCase(_state.uow, FakeGateway(), _state.notifier, FixedClock()),
)
dependency_provider.override(deps.get_retry_publisher, lambda **_: _state.retry)


@pytest.fixture
def env():
    _state.uow, _state.notifier, _state.retry = FakeUnitOfWork(), FakeNotifier(), _RecordingRetry()
    return _state.uow, _state.notifier, _state.retry


async def test_message_is_processed(env, make_payment):
    uow, notifier, retry = env
    p = make_payment()
    await uow.payments.add(p)

    async with TestRabbitBroker(broker) as br:
        await br.publish({"payment_id": str(p.id)}, exchange=payments_exchange, routing_key=new_queue.routing)

    assert uow.payments.rows[p.id].status is Status.succeeded
    assert len(notifier.sent) == 1
    assert retry.calls == []


async def test_failure_goes_to_retry_with_attempt_from_header(env):
    _, _, retry = env
    missing = uuid.uuid4()

    async with TestRabbitBroker(broker) as br:
        await br.publish(
            {"payment_id": str(missing)},
            exchange=payments_exchange,
            routing_key=new_queue.routing,
            headers={"x-attempt": 2},
        )

    assert len(retry.calls) == 1
    body, attempt, error = retry.calls[0]
    assert body == {"payment_id": str(missing)} and attempt == 2 and "not found" in error
