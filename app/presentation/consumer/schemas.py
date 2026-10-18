import uuid

from pydantic import BaseModel


class PaymentCreatedEvent(BaseModel):
    """Тело сообщения в очереди payments.new."""

    payment_id: uuid.UUID
