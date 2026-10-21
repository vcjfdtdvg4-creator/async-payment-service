from dataclasses import dataclass

from app.domain.payments.entity import Payment
from app.domain.payments.values import Status
from app.domain.ports.uow import UnitOfWork


@dataclass(frozen=True)
class ListPaymentsQuery:
    page: int = 1
    page_size: int = 25
    status: Status | None = None
    search: str | None = None


@dataclass(frozen=True)
class PaymentsPage:
    items: list[Payment]
    total: int
    page: int
    total_pages: int
    stats: dict[Status, int]


class ListPaymentsUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, query: ListPaymentsQuery) -> PaymentsPage:
        size = query.page_size
        async with self._uow:
            items = await self._uow.payments.list(
                status=query.status,
                search=query.search,
                offset=(query.page - 1) * size,
                limit=size,
            )
            total = await self._uow.payments.count(status=query.status, search=query.search)
            counts = await self._uow.payments.count_by_status()

        return PaymentsPage(
            items=items,
            total=total,
            page=query.page,
            total_pages=max(1, (total + size - 1) // size),
            stats={s: counts.get(s, 0) for s in Status},
        )
