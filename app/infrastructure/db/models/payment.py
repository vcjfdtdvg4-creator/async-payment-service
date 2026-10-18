import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base

IDEMPOTENCY_KEY_CONSTRAINT = "uq_payments_idempotency_key"


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name=IDEMPOTENCY_KEY_CONSTRAINT),
        CheckConstraint("status IN ('pending','succeeded','failed')", name="ck_payments_status"),
        CheckConstraint("currency IN ('RUB','USD','EUR')", name="ck_payments_currency"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    # "metadata" зарезервировано в Declarative, поэтому атрибут называется meta
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
