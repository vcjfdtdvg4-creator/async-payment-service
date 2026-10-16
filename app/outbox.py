"""Outbox relay: читает неопубликованные события из БД и публикует их в RabbitMQ.

Гарантия: at-least-once. Событие помечается published_at только после подтверждения
брокера (publisher confirms). SELECT ... FOR UPDATE SKIP LOCKED позволяет безопасно
запускать несколько экземпляров relay.
"""
import asyncio
import logging
from datetime import datetime, timezone

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.messaging import EXCHANGE, ROUTING_KEY, declare_topology
from app.models import OutboxEvent

logger = logging.getLogger("outbox")


async def publish_batch(broker: RabbitBroker) -> int:
    published = 0
    async with SessionLocal() as session, session.begin():
        rows = (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(settings.outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for row in rows:
            try:
                await broker.publish(
                    row.payload,
                    exchange=EXCHANGE,
                    routing_key=ROUTING_KEY,
                    persist=True,
                    message_id=str(row.id),
                )
            except Exception:
                logger.exception("Publish failed, will retry later (event=%s)", row.id)
                break  # уже опубликованные в этом батче фиксируем коммитом
            row.published_at = datetime.now(timezone.utc)
            published += 1
    return published


async def run_relay(stop: asyncio.Event) -> None:
    reconnects = 0
    while not stop.is_set():
        broker = RabbitBroker(settings.rabbitmq_url)
        try:
            await broker.start()
            await declare_topology(broker)
            logger.info("Outbox relay started")
            failures = 0
            while not stop.is_set():
                try:
                    n = await publish_batch(broker)
                    failures = 0
                    reconnects = 0
                except Exception:
                    logger.exception("Outbox batch failed")
                    failures += 1
                    if failures >= 5:
                        raise  # во внешний except -> пересоздать broker
                    n = 0
                if n == 0:
                    try:
                        await asyncio.wait_for(stop.wait(), settings.outbox_poll_interval_seconds)
                    except asyncio.TimeoutError:
                        pass
        except Exception:
            reconnects += 1
            delay = min(3 * reconnects, 15)
            logger.exception("Outbox relay lost broker connection, reconnecting in %ds", delay)
            await asyncio.sleep(delay)
        finally:
            try:
                await broker.close()
            except Exception:
                pass
