from decimal import Decimal

import pytest

from app.application.payments.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.domain.payments.events import PaymentCreated
from app.domain.payments.exceptions import IdempotencyConflictError
from app.domain.payments.values import Currency, Status
from tests.fakes import FakeUnitOfWork


def _cmd(**overrides) -> CreatePaymentCommand:
    data = dict(
        amount=Decimal("100.00"),
        currency=Currency.RUB,
        description="Order #1",
        metadata={"order_id": 1},
        webhook_url="https://example.com/hook",
        idempotency_key="key-1",
    )
    data.update(overrides)
    return CreatePaymentCommand(**data)


async def test_creates_payment_and_outbox_event():
    uow = FakeUnitOfWork()
    result = await CreatePaymentUseCase(uow).execute(_cmd())

    assert result.created
    assert result.status is Status.pending
    assert result.created_at is not None
    assert uow.commits == 1
    assert uow.outbox == [PaymentCreated(payment_id=result.payment_id)]


async def test_same_key_same_body_returns_existing_payment():
    uow = FakeUnitOfWork()
    use_case = CreatePaymentUseCase(uow)
    first = await use_case.execute(_cmd())
    second = await use_case.execute(_cmd())

    assert not second.created
    assert second.payment_id == first.payment_id
    assert len(uow.payments.rows) == 1
    assert len(uow.outbox) == 1


async def test_same_key_different_body_conflicts():
    uow = FakeUnitOfWork()
    use_case = CreatePaymentUseCase(uow)
    await use_case.execute(_cmd())
    with pytest.raises(IdempotencyConflictError):
        await use_case.execute(_cmd(amount=Decimal("999")))


async def test_race_on_insert_returns_payment_from_parallel_request(make_payment):
    uow = FakeUnitOfWork()
    winner = make_payment(meta={"order_id": 1})
    uow.payments.race_with = winner

    result = await CreatePaymentUseCase(uow).execute(_cmd())

    assert not result.created
    assert result.payment_id == winner.id
    assert uow.commits == 0


async def test_race_with_different_body_conflicts(make_payment):
    uow = FakeUnitOfWork()
    uow.payments.race_with = make_payment(description="other")
    with pytest.raises(IdempotencyConflictError):
        await CreatePaymentUseCase(uow).execute(_cmd())
