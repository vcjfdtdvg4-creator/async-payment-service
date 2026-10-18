import asyncio
import random

from app.domain.payments.entity import Payment
from app.domain.payments.values import Status


class EmulatedPaymentGateway:
    """Эмуляция внешнего шлюза: задержка 2–5 с, 90 % succeeded / 10 % failed."""

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        success_rate: float = 0.9,
        rng: random.Random | None = None,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate
        self._rng = rng or random.Random()

    async def charge(self, payment: Payment) -> Status:
        await asyncio.sleep(self._rng.uniform(self._min_delay, self._max_delay))
        return Status.succeeded if self._rng.random() < self._success_rate else Status.failed
