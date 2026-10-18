from types import TracebackType
from typing import Protocol, Self

from app.domain.ports.repositories.payment import PaymentRepository


class UnitOfWork(Protocol):
    payments: PaymentRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
