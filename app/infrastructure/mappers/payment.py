from decimal import Decimal

from app.domain.payments.entity import Payment
from app.domain.payments.values import Currency, Status
from app.infrastructure.db.models.payment import PaymentModel


def to_entity(model: PaymentModel) -> Payment:
    return Payment(
        id=model.id,
        amount=Decimal(model.amount),
        currency=Currency(model.currency),
        description=model.description,
        idempotency_key=model.idempotency_key,
        webhook_url=model.webhook_url,
        meta=dict(model.meta or {}),
        status=Status(model.status),
        created_at=model.created_at,
        processed_at=model.processed_at,
        webhook_delivered_at=model.webhook_delivered_at,
    )


def to_model(payment: Payment) -> PaymentModel:
    return PaymentModel(
        id=payment.id,
        amount=payment.amount,
        currency=payment.currency.value,
        description=payment.description,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        meta=payment.meta,
        status=payment.status.value,
        processed_at=payment.processed_at,
        webhook_delivered_at=payment.webhook_delivered_at,
    )
