import httpx
from faststream import Context, Depends

from app.application.payments.process_payment import ProcessPaymentUseCase
from app.config import settings
from app.domain.ports.clock import UtcClock
from app.infrastructure.broker.connection import broker
from app.infrastructure.broker.retry import RetryPublisher
from app.infrastructure.db.session import session_factory
from app.infrastructure.gateway.emulator import EmulatedPaymentGateway
from app.infrastructure.uow import SqlAlchemyUnitOfWork
from app.infrastructure.webhooks.client import HttpWebhookNotifier

_gateway = EmulatedPaymentGateway()


# FastDepends валидирует аннотации зависимостей через isinstance,
# поэтому здесь конкретный класс, а не Protocol UnitOfWork.
def get_uow() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory)


def get_process_payment_use_case(
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    http_client: httpx.AsyncClient = Context("http_client"),
) -> ProcessPaymentUseCase:
    return ProcessPaymentUseCase(
        uow=uow,
        gateway=_gateway,
        notifier=HttpWebhookNotifier(http_client),
        clock=UtcClock(),
    )


def get_retry_publisher() -> RetryPublisher:
    return RetryPublisher(broker, max_attempts=settings.max_attempts)
