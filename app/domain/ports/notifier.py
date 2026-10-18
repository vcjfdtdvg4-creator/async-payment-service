from typing import Protocol

from app.domain.payments.entity import Payment


class PaymentNotifier(Protocol):
    """Уведомляет клиента о результате. Бросает исключение, если доставка не удалась."""

    async def notify(self, payment: Payment) -> None: ...
