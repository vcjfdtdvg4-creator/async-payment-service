"""Топология RabbitMQ — общая для API (outbox relay) и consumer.

payments (direct exchange) --payments.new--> payments.new (queue)
        при ошибке обработки consumer публикует сообщение в
        payments.new.retry.N (TTL = base * 2^(N-1), по истечении TTL возвращается
        в exchange payments), а после исчерпания попыток -- в payments.dlq.
        Если сообщение отвергнуто (reject), main-очередь сама отправляет его в DLQ
        через dead-letter-exchange.
"""
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings

ROUTING_KEY = "payments.new"
DLQ_NAME = "payments.dlq"

EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)

MAIN_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": "",           # default exchange
        "x-dead-letter-routing-key": DLQ_NAME,  # -> payments.dlq
    },
)

DLQ = RabbitQueue(DLQ_NAME, durable=True)


def retry_delay_seconds(attempt: int) -> int:
    """Задержка перед следующей попыткой после неудачной попытки №attempt."""
    return settings.retry_base_delay_seconds * 2 ** (attempt - 1)


def retry_queue_name(attempt: int) -> str:
    return f"payments.new.retry.{attempt}"


def retry_queues() -> list[RabbitQueue]:
    # N попыток => N-1 повторов => N-1 retry-очередей (отдельная очередь на каждую
    # задержку, чтобы не было head-of-line blocking из-за разных TTL).
    return [
        RabbitQueue(
            retry_queue_name(a),
            durable=True,
            arguments={
                "x-message-ttl": retry_delay_seconds(a) * 1000,
                "x-dead-letter-exchange": EXCHANGE.name,
                "x-dead-letter-routing-key": ROUTING_KEY,
            },
        )
        for a in range(1, settings.max_attempts)
    ]


async def declare_topology(broker: RabbitBroker) -> None:
    """Идемпотентно объявляет exchange, очереди и binding."""
    exchange = await broker.declare_exchange(EXCHANGE)
    main = await broker.declare_queue(MAIN_QUEUE)
    await main.bind(exchange, routing_key=ROUTING_KEY)
    await broker.declare_queue(DLQ)
    for q in retry_queues():
        await broker.declare_queue(q)
