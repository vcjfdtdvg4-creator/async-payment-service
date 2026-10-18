from fastapi import Depends

from app.application.admin.list_payments import ListPaymentsUseCase
from app.application.admin.payment_details import GetPaymentDetailsUseCase, ListOutboxUseCase
from app.application.admin.ports import OutboxReader
from app.application.admin.queues import QueueAdminUseCase
from app.application.payments.create_payment import CreatePaymentUseCase
from app.config import settings
from app.domain.ports.uow import UnitOfWork
from app.infrastructure.broker.publisher import RabbitPaymentEventPublisher
from app.infrastructure.broker.topology import DLQ_NAME
from app.infrastructure.db.session import session_factory
from app.infrastructure.rabbitmq_management.client import RabbitManagementQueueAdmin
from app.infrastructure.repositories.outbox import SqlAlchemyOutboxReader
from app.presentation.api.deps.core import get_uow


def get_outbox_reader() -> OutboxReader:
    return SqlAlchemyOutboxReader(session_factory)


def get_list_payments_use_case(uow: UnitOfWork = Depends(get_uow)) -> ListPaymentsUseCase:
    return ListPaymentsUseCase(uow)


def get_create_payment_use_case(uow: UnitOfWork = Depends(get_uow)) -> CreatePaymentUseCase:
    return CreatePaymentUseCase(uow)


def get_payment_details_use_case(
    uow: UnitOfWork = Depends(get_uow),
    outbox: OutboxReader = Depends(get_outbox_reader),
) -> GetPaymentDetailsUseCase:
    return GetPaymentDetailsUseCase(uow, outbox)


def get_list_outbox_use_case(outbox: OutboxReader = Depends(get_outbox_reader)) -> ListOutboxUseCase:
    return ListOutboxUseCase(outbox)


def get_queue_admin_use_case() -> QueueAdminUseCase:
    return QueueAdminUseCase(
        admin=RabbitManagementQueueAdmin(
            settings.rabbitmq_management_url,
            settings.rabbitmq_management_user,
            settings.rabbitmq_management_password,
        ),
        publisher=RabbitPaymentEventPublisher(settings.rabbitmq_url),
        dlq_name=DLQ_NAME,
    )
