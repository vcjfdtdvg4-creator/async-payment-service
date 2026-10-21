from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings

NEW_ROUTING_KEY = "payments.new"
DLQ_NAME = "payments.dlq"

payments_exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)

new_queue = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": DLQ_NAME,
    },
)

dlq = RabbitQueue(DLQ_NAME, durable=True)


def retry_delay_seconds(attempt: int) -> int:
    return settings.retry_base_delay_seconds * 2 ** (attempt - 1)


def retry_queue_name(attempt: int) -> str:
    return f"payments.new.retry.{attempt}"


def retry_queues() -> list[RabbitQueue]:
    return [
        RabbitQueue(
            retry_queue_name(a),
            durable=True,
            arguments={
                "x-message-ttl": retry_delay_seconds(a) * 1000,
                "x-dead-letter-exchange": payments_exchange.name,
                "x-dead-letter-routing-key": NEW_ROUTING_KEY,
            },
        )
        for a in range(1, settings.max_attempts)
    ]


async def declare_topology(broker: RabbitBroker) -> None:
    exchange = await broker.declare_exchange(payments_exchange)
    main = await broker.declare_queue(new_queue)
    await main.bind(exchange, routing_key=NEW_ROUTING_KEY)
    await broker.declare_queue(dlq)
    for q in retry_queues():
        await broker.declare_queue(q)
