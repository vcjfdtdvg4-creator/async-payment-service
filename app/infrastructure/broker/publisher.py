from typing import Any

from faststream.rabbit import RabbitBroker

from app.infrastructure.broker.topology import NEW_ROUTING_KEY, payments_exchange


class RabbitPaymentEventPublisher:
    def __init__(self, rabbitmq_url: str) -> None:
        self._url = rabbitmq_url

    async def publish_new(self, payloads: list[dict[str, Any]], headers: dict[str, Any]) -> None:
        broker = RabbitBroker(self._url)
        await broker.connect()
        try:
            for payload in payloads:
                await broker.publish(
                    payload,
                    exchange=payments_exchange,
                    routing_key=NEW_ROUTING_KEY,
                    persist=True,
                    headers=headers,
                )
        finally:
            await broker.close()
