from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.application.payments.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.application.payments.get_payment import GetPaymentCommand, GetPaymentUseCase
from app.presentation.api.deps.auth import verify_api_key
from app.presentation.api.deps.payments import get_create_payment_use_case, get_get_payment_use_case
from app.presentation.api.presenters.payments import create_result_to_response, payment_to_response
from app.presentation.api.schemas.payments import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"], dependencies=[Depends(verify_api_key)])

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreatePaymentResponse)
async def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: IdempotencyKey,
    use_case: CreatePaymentUseCase = Depends(get_create_payment_use_case),
) -> CreatePaymentResponse:
    result = await use_case.execute(
        CreatePaymentCommand(
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata=body.metadata,
            webhook_url=str(body.webhook_url),
            idempotency_key=idempotency_key,
        )
    )
    return create_result_to_response(result)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    use_case: GetPaymentUseCase = Depends(get_get_payment_use_case),
) -> PaymentResponse:
    payment = await use_case.execute(GetPaymentCommand(payment_id=payment_id))
    return payment_to_response(payment)
