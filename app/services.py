"""Общая бизнес-логика, используемая и API, и UI."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, Payment
from app.schemas import PaymentCreate


async def find_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    return (
        await session.execute(select(Payment).where(Payment.idempotency_key == key))
    ).scalar_one_or_none()


async def create_payment(session: AsyncSession, body: PaymentCreate, idempotency_key: str) -> Payment:
    """Идемпотентно создаёт платёж + outbox-событие в одной транзакции.

    Если платёж с таким ключом уже есть (в том числе из-за гонки), возвращает его.
    Сверка тела запроса -- ответственность вызывающего кода.
    """
    if (existing := await find_by_idempotency_key(session, idempotency_key)) is not None:
        return existing

    payment = Payment(
        id=uuid.uuid4(),
        amount=body.amount,
        currency=body.currency.value,
        description=body.description,
        meta=body.metadata,
        idempotency_key=idempotency_key,
        webhook_url=str(body.webhook_url),
    )
    session.add(payment)
    # Платёж и событие -- в ОДНОЙ транзакции (Outbox pattern).
    session.add(OutboxEvent(event_type="payment.created", payload={"payment_id": str(payment.id)}))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await find_by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        return existing
    await session.refresh(payment)
    return payment
