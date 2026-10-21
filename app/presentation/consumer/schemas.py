import uuid

from pydantic import BaseModel


class PaymentCreatedEvent(BaseModel):
    payment_id: uuid.UUID
