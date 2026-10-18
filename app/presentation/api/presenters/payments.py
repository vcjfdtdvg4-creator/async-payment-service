from app.application.payments.create_payment import CreatePaymentResult
from app.domain.payments.entity import Payment
from app.presentation.api.schemas.payments import CreatePaymentResponse, PaymentResponse


def payment_to_response(p: Payment) -> PaymentResponse:
    return PaymentResponse(
        payment_id=p.id,
        amount=p.amount,
        currency=p.currency,
        description=p.description,
        metadata=p.meta,
        status=p.status,
        idempotency_key=p.idempotency_key,
        webhook_url=p.webhook_url,
        created_at=p.created_at,
        processed_at=p.processed_at,
    )


def create_result_to_response(result: CreatePaymentResult) -> CreatePaymentResponse:
    return CreatePaymentResponse(
        payment_id=result.payment_id,
        status=result.status,
        created_at=result.created_at,
    )
