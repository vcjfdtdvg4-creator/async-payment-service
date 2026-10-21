from typing import Protocol

from app.domain.payments.entity import Payment


class PaymentNotifier(Protocol):
    async def notify(self, payment: Payment) -> None: ...
