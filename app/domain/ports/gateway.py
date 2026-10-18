from typing import Protocol

from app.domain.payments.entity import Payment
from app.domain.payments.values import Status


class PaymentGateway(Protocol):
    async def charge(self, payment: Payment) -> Status: ...
