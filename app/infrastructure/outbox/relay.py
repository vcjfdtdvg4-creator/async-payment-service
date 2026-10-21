import asyncio
import logging
from datetime import datetime, timezone

from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.broker.topology import NEW_ROUTING_KEY, payments_exchange
from app.infrastructure.repositories.outbox import SqlAlchemyOutboxRepository

logger = logging.getLogger(__name__)

ROUTING_BY_EVENT: dict[str, str] = {
    "payment.created": NEW_ROUTING_KEY,
}


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broker: RabbitBroker,
        batch_size: int = 50,
        poll_interval: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        logger.info("Outbox relay started")
        while not self._stop.is_set():
            try:
                published = await self.publish_batch()
            except Exception:
                logger.exception("Outbox relay iteration failed")
                published = 0
            if published == 0:
                try:
                    await asyncio.wait_for(self._stop.wait(), self._poll_interval)
                except asyncio.TimeoutError:
                    pass

    async def publish_batch(self) -> int:
        async with self._session_factory() as session, session.begin():
            outbox = SqlAlchemyOutboxRepository(session)
            messages = await outbox.fetch_unpublished(limit=self._batch_size)

            published_ids = []
            for message in messages:
                try:
                    await self._broker.publish(
                        message.payload,
                        exchange=payments_exchange,
                        routing_key=ROUTING_BY_EVENT[message.event_type],
                        message_id=str(message.id),
                        persist=True,
                    )
                except Exception:
                    logger.exception("Publish failed, will retry later (event=%s)", message.id)
                    break
                published_ids.append(message.id)

            await outbox.mark_published(published_ids, datetime.now(timezone.utc))
        return len(published_ids)
