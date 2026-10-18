import logging

from faststream import Depends
from faststream.rabbit import RabbitMessage, RabbitRouter

from app.application.payments.process_payment import ProcessPaymentUseCase
from app.infrastructure.broker.retry import RetryPublisher, attempt_from_headers
from app.infrastructure.broker.topology import new_queue, payments_exchange
from app.presentation.consumer.deps import get_process_payment_use_case, get_retry_publisher
from app.presentation.consumer.schemas import PaymentCreatedEvent

logger = logging.getLogger(__name__)

router = RabbitRouter()


@router.subscriber(new_queue, payments_exchange)
async def handle_payment_created(
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    use_case: ProcessPaymentUseCase = Depends(get_process_payment_use_case, cast=False),
    retry: RetryPublisher = Depends(get_retry_publisher, cast=False),
) -> None:
    attempt = attempt_from_headers(message.headers)
    try:
        await use_case.execute(event.payment_id)
    except Exception as exc:  # noqa: BLE001
        # Если публикация retry/DLQ тоже упадёт, исключение уйдёт наружу -> reject ->
        # main-очередь отправит сообщение в DLQ через dead-letter-exchange.
        await retry.reroute({"payment_id": str(event.payment_id)}, attempt, exc)
