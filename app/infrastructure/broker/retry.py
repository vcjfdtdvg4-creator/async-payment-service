import logging
from collections.abc import Mapping
from typing import Any

from faststream.rabbit import RabbitBroker

from app.infrastructure.broker.topology import DLQ_NAME, retry_delay_seconds, retry_queue_name

logger = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"
LAST_ERROR_HEADER = "x-last-error"


def attempt_from_headers(headers: Mapping[str, Any] | None) -> int:
    try:
        return max(1, int((headers or {}).get(ATTEMPT_HEADER, 1)))
    except (TypeError, ValueError):
        return 1


class RetryPublisher:
    def __init__(self, broker: RabbitBroker, max_attempts: int) -> None:
        self._broker = broker
        self._max_attempts = max_attempts

    async def reroute(self, body: dict[str, Any], attempt: int, exc: BaseException) -> None:
        error = repr(exc)[:500]
        if attempt >= self._max_attempts:
            logger.error("Message %s failed after %d attempts -> DLQ: %s", body, attempt, error)
            await self._broker.publish(
                body,
                queue=DLQ_NAME,
                persist=True,
                headers={ATTEMPT_HEADER: attempt, LAST_ERROR_HEADER: error},
            )
            return

        logger.warning(
            "Attempt %d for %s failed (%s); retry in %ds", attempt, body, error, retry_delay_seconds(attempt)
        )
        await self._broker.publish(
            body,
            queue=retry_queue_name(attempt),
            persist=True,
            headers={ATTEMPT_HEADER: attempt + 1, LAST_ERROR_HEADER: error},
        )
