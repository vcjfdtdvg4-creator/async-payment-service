from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.admin.ports import OutboxEntry
from app.infrastructure.db.models.outbox import OutboxModel
from app.infrastructure.mappers.outbox import to_entry, to_message, to_model
from app.infrastructure.outbox.message import OutboxMessage


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> None:
        self._session.add(to_model(message))

    async def fetch_unpublished(self, limit: int) -> list[OutboxMessage]:
        rows = await self._session.scalars(
            select(OutboxModel)
            .where(OutboxModel.published_at.is_(None))
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [to_message(m) for m in rows.all()]

    async def mark_published(self, ids: list[UUID], published_at: datetime) -> None:
        if ids:
            await self._session.execute(
                update(OutboxModel).where(OutboxModel.id.in_(ids)).values(published_at=published_at)
            )


class SqlAlchemyOutboxReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_recent(self, limit: int) -> list[OutboxEntry]:
        async with self._session_factory() as session:
            rows = await session.scalars(select(OutboxModel).order_by(desc(OutboxModel.created_at)).limit(limit))
            return [to_entry(m) for m in rows.all()]

    async def list_for_payment(self, payment_id: UUID) -> list[OutboxEntry]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(OutboxModel)
                .where(OutboxModel.payload["payment_id"].astext == str(payment_id))
                .order_by(desc(OutboxModel.created_at))
            )
            return [to_entry(m) for m in rows.all()]
