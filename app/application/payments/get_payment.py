from dataclasses import dataclass
from uuid import UUID

from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import PaymentNotFoundError
from app.domain.ports.uow import UnitOfWork


@dataclass(frozen=True)
class GetPaymentCommand:
    payment_id: UUID


class GetPaymentUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, cmd: GetPaymentCommand) -> Payment:
        async with self._uow:
            payment = await self._uow.payments.get(cmd.payment_id)
        if payment is None:
            raise PaymentNotFoundError(cmd.payment_id)
        return payment
