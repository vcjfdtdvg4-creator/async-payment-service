from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payments.entity import Payment
from app.domain.payments.exceptions import DuplicateIdempotencyKeyError
from app.domain.payments.values import Status
from app.infrastructure.db.models.payment import IDEMPOTENCY_KEY_CONSTRAINT, PaymentModel
from app.infrastructure.mappers.payment import to_entity, to_model


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.seen: list[Payment] = []

    async def add(self, payment: Payment) -> None:
        model = to_model(payment)
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as e:
            if IDEMPOTENCY_KEY_CONSTRAINT in str(e.orig):
                raise DuplicateIdempotencyKeyError(payment.idempotency_key) from e
            raise
        await self._session.refresh(model)
        payment.created_at = model.created_at
        self.seen.append(payment)

    async def get(self, payment_id: UUID) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id, populate_existing=True)
        return to_entity(model) if model else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        model = await self._session.scalar(select(PaymentModel).where(PaymentModel.idempotency_key == key))
        return to_entity(model) if model else None

    async def mark_processed(self, payment_id: UUID, status: Status, processed_at: datetime) -> bool:
        result = await self._session.execute(
            update(PaymentModel)
            .where(PaymentModel.id == payment_id, PaymentModel.status == Status.pending.value)
            .values(status=status.value, processed_at=processed_at)
        )
        return result.rowcount > 0

    async def mark_webhook_delivered(self, payment_id: UUID, delivered_at: datetime) -> None:
        await self._session.execute(
            update(PaymentModel).where(PaymentModel.id == payment_id).values(webhook_delivered_at=delivered_at)
        )

    async def list(self, *, status: Status | None, search: str | None, offset: int, limit: int) -> list[Payment]:
        stmt = self._filtered(select(PaymentModel), status, search)
        stmt = stmt.order_by(desc(PaymentModel.created_at)).offset(offset).limit(limit)
        return [to_entity(m) for m in (await self._session.scalars(stmt)).all()]

    async def count(self, *, status: Status | None, search: str | None) -> int:
        stmt = self._filtered(select(func.count()).select_from(PaymentModel), status, search)
        return int(await self._session.scalar(stmt) or 0)

    async def count_by_status(self) -> dict[Status, int]:
        rows = await self._session.execute(
            select(PaymentModel.status, func.count()).group_by(PaymentModel.status)
        )
        return {Status(status): count for status, count in rows.all()}

    @staticmethod
    def _filtered(stmt: Select, status: Status | None, search: str | None) -> Select:
        if status is not None:
            stmt = stmt.where(PaymentModel.status == status.value)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(PaymentModel.description.ilike(like), PaymentModel.idempotency_key.ilike(like)))
        return stmt
