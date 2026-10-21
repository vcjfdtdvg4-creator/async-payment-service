import logging
from uuid import UUID

from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import PaymentNotFoundError
from app.domain.ports.clock import Clock
from app.domain.ports.gateway import PaymentGateway
from app.domain.ports.notifier import PaymentNotifier
from app.domain.ports.uow import UnitOfWork

logger = logging.getLogger(__name__)


class ProcessPaymentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        gateway: PaymentGateway,
        notifier: PaymentNotifier,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._gateway = gateway
        self._notifier = notifier
        self._clock = clock

    async def execute(self, payment_id: UUID) -> None:
        payment = await self._load(payment_id)

        if not payment.is_final:
            status = await self._gateway.charge(payment)
            async with self._uow:
                await self._uow.payments.mark_processed(payment.id, status, self._clock.now())
                await self._uow.commit()
            payment = await self._load(payment_id)
            logger.info("Payment %s processed: %s", payment_id, payment.status)

        if not payment.is_webhook_delivered:
            await self._notifier.notify(payment)
            async with self._uow:
                await self._uow.payments.mark_webhook_delivered(payment.id, self._clock.now())
                await self._uow.commit()
            logger.info("Webhook delivered for payment %s", payment_id)

    async def _load(self, payment_id: UUID) -> Payment:
        async with self._uow:
            payment = await self._uow.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment
