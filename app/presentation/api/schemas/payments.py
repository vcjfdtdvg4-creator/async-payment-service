import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field

from app.domain.payments.values import Currency, Status


class CreatePaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str = Field(min_length=1, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: AnyHttpUrl


class CreatePaymentResponse(BaseModel):
    payment_id: uuid.UUID
    status: Status
    created_at: datetime | None


class PaymentResponse(BaseModel):
    payment_id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: Status
    idempotency_key: str
    webhook_url: str
    created_at: datetime | None
    processed_at: datetime | None
