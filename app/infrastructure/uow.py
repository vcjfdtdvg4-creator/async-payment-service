from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.outbox.serializer import to_outbox_message
from app.infrastructure.repositories.outbox import SqlAlchemyOutboxRepository
from app.infrastructure.repositories.payments import SqlAlchemyPaymentRepository


class SqlAlchemyUnitOfWork:
    """Транзакция над payments + outbox (Outbox pattern: платёж и событие пишутся атомарно)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.payments = SqlAlchemyPaymentRepository(self._session)
        self._outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._save_events()
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def _save_events(self) -> None:
        for payment in self.payments.seen:
            for event in payment.pull_events():
                await self._outbox.add(to_outbox_message(event))
