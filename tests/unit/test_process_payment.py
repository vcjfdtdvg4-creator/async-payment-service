import uuid

import pytest

from app.application.payments.process_payment import ProcessPaymentUseCase
from app.domain.payments.exceptions import PaymentNotFoundError
from app.domain.payments.values import Status
from tests.fakes import NOW, FakeGateway, FakeNotifier, FakeUnitOfWork, FixedClock


async def _stored(uow, payment):
    await uow.payments.add(payment)
    return payment.id


def _use_case(uow, gateway=None, notifier=None):
    return ProcessPaymentUseCase(uow, gateway or FakeGateway(), notifier or FakeNotifier(), FixedClock())


@pytest.mark.parametrize("outcome", [Status.succeeded, Status.failed])
async def test_charges_and_notifies(make_payment, outcome):
    uow, gateway, notifier = FakeUnitOfWork(), FakeGateway(outcome), FakeNotifier()
    pid = await _stored(uow, make_payment())

    await _use_case(uow, gateway, notifier).execute(pid)

    stored = uow.payments.rows[pid]
    assert stored.status is outcome
    assert stored.processed_at == NOW
    assert stored.webhook_delivered_at == NOW
    assert [p.status for p in notifier.sent] == [outcome]


async def test_redelivery_does_not_recharge_or_resend(make_payment):
    uow, gateway, notifier = FakeUnitOfWork(), FakeGateway(), FakeNotifier()
    pid = await _stored(uow, make_payment())
    use_case = _use_case(uow, gateway, notifier)

    await use_case.execute(pid)
    await use_case.execute(pid)

    assert len(gateway.calls) == 1
    assert len(notifier.sent) == 1


async def test_webhook_failure_keeps_status_and_retries_only_webhook(make_payment):
    uow, gateway = FakeUnitOfWork(), FakeGateway()
    pid = await _stored(uow, make_payment())

    with pytest.raises(ConnectionError):
        await _use_case(uow, gateway, FakeNotifier(fail=True)).execute(pid)
    assert uow.payments.rows[pid].status is Status.succeeded
    assert uow.payments.rows[pid].webhook_delivered_at is None

    notifier = FakeNotifier()
    await _use_case(uow, gateway, notifier).execute(pid)
    assert len(gateway.calls) == 1  # статус не пересчитан
    assert len(notifier.sent) == 1


async def test_unknown_payment_raises():
    with pytest.raises(PaymentNotFoundError):
        await _use_case(FakeUnitOfWork()).execute(uuid.uuid4())
