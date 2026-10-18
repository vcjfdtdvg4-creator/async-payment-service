from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import DuplicateIdempotencyKeyError, IdempotencyConflictError
from app.domain.payments.values import Currency, Status
from app.domain.ports.uow import UnitOfWork


@dataclass(frozen=True)
class CreatePaymentCommand:
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str


@dataclass(frozen=True)
class CreatePaymentResult:
    payment_id: UUID
    status: Status
    created_at: datetime | None
    created: bool  # False -> вернули уже существующий платёж


class CreatePaymentUseCase:
    """Идемпотентно создаёт платёж; событие PaymentCreated уходит в outbox в той же транзакции.

    Повтор с тем же ключом и тем же телом возвращает существующий платёж,
    с другим телом -- IdempotencyConflictError.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, cmd: CreatePaymentCommand) -> CreatePaymentResult:
        try:
            async with self._uow:
                existing = await self._uow.payments.get_by_idempotency_key(cmd.idempotency_key)
                if existing is not None:
                    return self._replay(existing, cmd)

                payment = Payment.create(
                    amount=cmd.amount,
                    currency=cmd.currency,
                    description=cmd.description,
                    meta=cmd.metadata,
                    webhook_url=cmd.webhook_url,
                    idempotency_key=cmd.idempotency_key,
                )
                await self._uow.payments.add(payment)
                await self._uow.commit()
        except DuplicateIdempotencyKeyError:
            # гонка одинаковых запросов: платёж вставил параллельный запрос
            async with self._uow:
                existing = await self._uow.payments.get_by_idempotency_key(cmd.idempotency_key)
            if existing is None:
                raise
            return self._replay(existing, cmd)

        return CreatePaymentResult(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
            created=True,
        )

    @staticmethod
    def _replay(existing: Payment, cmd: CreatePaymentCommand) -> CreatePaymentResult:
        same = existing.matches(
            amount=cmd.amount,
            currency=cmd.currency,
            description=cmd.description,
            webhook_url=cmd.webhook_url,
            meta=cmd.metadata,
        )
        if not same:
            raise IdempotencyConflictError(cmd.idempotency_key)
        return CreatePaymentResult(
            payment_id=existing.id,
            status=existing.status,
            created_at=existing.created_at,
            created=False,
        )
