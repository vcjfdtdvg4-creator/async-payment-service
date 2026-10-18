from dataclasses import dataclass
from uuid import UUID

from app.application.admin.ports import OutboxEntry, OutboxReader
from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import PaymentNotFoundError
from app.domain.ports.uow import UnitOfWork


@dataclass(frozen=True)
class PaymentDetails:
    payment: Payment
    events: list[OutboxEntry]


class GetPaymentDetailsUseCase:
    def __init__(self, uow: UnitOfWork, outbox: OutboxReader) -> None:
        self._uow = uow
        self._outbox = outbox

    async def execute(self, payment_id: UUID) -> PaymentDetails:
        async with self._uow:
            payment = await self._uow.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return PaymentDetails(payment=payment, events=await self._outbox.list_for_payment(payment_id))


class ListOutboxUseCase:
    def __init__(self, outbox: OutboxReader, limit: int = 100) -> None:
        self._outbox = outbox
        self._limit = limit

    async def execute(self) -> list[OutboxEntry]:
        return await self._outbox.list_recent(self._limit)
