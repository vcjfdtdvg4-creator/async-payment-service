"""Единственный consumer: обработка платежа -> обновление БД -> webhook, с retry и DLQ."""
import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone

from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage
from sqlalchemy import update

from app.config import settings
from app.db import SessionLocal
from app.messaging import DLQ_NAME, EXCHANGE, MAIN_QUEUE, declare_topology, retry_delay_seconds, retry_queue_name
from app.models import Payment, PaymentStatus
from app.schemas import PaymentEvent
from app.webhook import send_webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("consumer")

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)


@app.after_startup
async def _declare() -> None:
    await declare_topology(broker)


async def process_payment(payment_id: uuid.UUID) -> None:
    """Идемпотентна: повторная доставка не пересчитывает статус и не шлёт webhook повторно,
    если он уже доставлен."""
    async with SessionLocal() as session:
        payment = await session.get(Payment, payment_id)
    if payment is None:
        raise LookupError(f"Payment {payment_id} not found")

    if payment.status == PaymentStatus.PENDING.value:
        await asyncio.sleep(random.uniform(2, 5))                   # эмуляция шлюза
        outcome = PaymentStatus.SUCCEEDED if random.random() < 0.9 else PaymentStatus.FAILED
        async with SessionLocal() as session, session.begin():
            # условный UPDATE: при гонке дубликатов статус выставит только один
            await session.execute(
                update(Payment)
                .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING.value)
                .values(status=outcome.value, processed_at=datetime.now(timezone.utc))
            )
        async with SessionLocal() as session:
            payment = await session.get(Payment, payment_id)
        logger.info("Payment %s processed: %s", payment_id, payment.status)

    if payment.webhook_delivered_at is None:
        await send_webhook(payment)  # исключение -> retry всего сообщения
        async with SessionLocal() as session, session.begin():
            await session.execute(
                update(Payment).where(Payment.id == payment_id).values(webhook_delivered_at=datetime.now(timezone.utc))
            )
        logger.info("Webhook delivered for payment %s", payment_id)


async def retry_or_dead_letter(event: PaymentEvent, attempt: int, exc: Exception) -> None:
    body = {"payment_id": str(event.payment_id)}
    if attempt >= settings.max_attempts:
        logger.error("Payment %s failed after %d attempts -> DLQ: %s", event.payment_id, attempt, exc)
        await broker.publish(
            body, queue=DLQ_NAME, persist=True,
            headers={"x-attempt": attempt, "x-last-error": repr(exc)[:500]},
        )
        return
    delay = retry_delay_seconds(attempt)
    logger.warning("Attempt %d for payment %s failed (%r); retry in %ds", attempt, event.payment_id, exc, delay)
    await broker.publish(
        body, queue=retry_queue_name(attempt), persist=True,
        headers={"x-attempt": attempt + 1, "x-last-error": repr(exc)[:500]},
    )


def _attempt(headers: dict | None) -> int:
    try:
        return max(1, int((headers or {}).get("x-attempt", 1)))
    except (TypeError, ValueError):
        return 1


@broker.subscriber(MAIN_QUEUE, EXCHANGE)
async def handle_new_payment(event: PaymentEvent, message: RabbitMessage) -> None:
    attempt = _attempt(message.headers)
    try:
        await process_payment(event.payment_id)
    except Exception as exc:  # noqa: BLE001
        # Если публикация retry/DLQ тоже упадёт, исключение уйдёт наружу -> reject ->
        # main-очередь отправит сообщение в DLQ через dead-letter-exchange.
        await retry_or_dead_letter(event, attempt, exc)
