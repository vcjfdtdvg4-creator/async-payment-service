from fastapi import Depends

from app.application.payments.create_payment import CreatePaymentUseCase
from app.application.payments.get_payment import GetPaymentUseCase
from app.domain.ports.uow import UnitOfWork
from app.presentation.api.deps.core import get_uow


def get_get_payment_use_case(uow: UnitOfWork = Depends(get_uow)) -> GetPaymentUseCase:
    return GetPaymentUseCase(uow)


def get_create_payment_use_case(uow: UnitOfWork = Depends(get_uow)) -> CreatePaymentUseCase:
    return CreatePaymentUseCase(uow)
