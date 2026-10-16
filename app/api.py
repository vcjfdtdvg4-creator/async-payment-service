import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Payment
from app.schemas import PaymentAccepted, PaymentCreate, PaymentOut
from app.security import verify_api_key
from app.services import create_payment as create_payment_record

router = APIRouter(prefix="/api/v1/payments", tags=["payments"], dependencies=[Depends(verify_api_key)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


def _replay(existing: Payment, body: PaymentCreate) -> Payment:
    """Повторный запрос с тем же ключом: тело должно совпадать, иначе 409."""
    same = (
        existing.amount == body.amount
        and existing.currency == body.currency.value
        and existing.description == body.description
        and existing.meta == body.metadata
        and existing.webhook_url == str(body.webhook_url)
    )
    if not same:
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with a different request body")
    return existing


@router.post("", response_model=PaymentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(body: PaymentCreate, session: SessionDep, idempotency_key: IdempotencyKey):
    # Сервис идемпотентен (в т.ч. при гонке по unique(idempotency_key)) и возвращает
    # либо новый, либо уже существующий платёж; _replay бросает 409, если тело другое.
    payment = await create_payment_record(session, body, idempotency_key)
    return _replay(payment, body)


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: uuid.UUID, session: SessionDep):
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment
