import uuid
from datetime import datetime, timezone

import pytest

from app.application.admin.list_payments import ListPaymentsQuery, ListPaymentsUseCase
from app.application.admin.payment_details import GetPaymentDetailsUseCase
from app.application.admin.ports import OutboxEntry
from app.application.admin.queues import QueueAdminUseCase, RequeueNotAllowedError, UnknownQueueError
from app.domain.payments.exceptions import PaymentNotFoundError
from app.domain.payments.values import Status
from tests.fakes import FakeOutboxReader, FakePublisher, FakeQueueAdmin, FakeUnitOfWork


async def test_list_payments_filters_paginates_and_counts(make_payment):
    uow = FakeUnitOfWork()
    for i in range(5):
        p = make_payment(idempotency_key=f"k{i}", description=f"order {i}")
        if i < 2:
            p.status = Status.failed
        await uow.payments.add(p)

    page = await ListPaymentsUseCase(uow).execute(ListPaymentsQuery(page=2, page_size=2))
    assert page.total == 5 and page.total_pages == 3 and len(page.items) == 2
    assert page.stats == {Status.pending: 3, Status.succeeded: 0, Status.failed: 2}

    failed = await ListPaymentsUseCase(uow).execute(ListPaymentsQuery(status=Status.failed))
    assert failed.total == 2

    found = await ListPaymentsUseCase(uow).execute(ListPaymentsQuery(search="ORDER 3"))
    assert [p.idempotency_key for p in found.items] == ["k3"]


async def test_payment_details_include_outbox_events(make_payment):
    uow = FakeUnitOfWork()
    p = make_payment()
    await uow.payments.add(p)
    now = datetime.now(timezone.utc)
    mine = OutboxEntry(uuid.uuid4(), "payment.created", {"payment_id": str(p.id)}, now, None)
    other = OutboxEntry(uuid.uuid4(), "payment.created", {"payment_id": str(uuid.uuid4())}, now, None)

    details = await GetPaymentDetailsUseCase(uow, FakeOutboxReader([mine, other])).execute(p.id)
    assert details.payment.id == p.id
    assert details.events == [mine]

    with pytest.raises(PaymentNotFoundError):
        await GetPaymentDetailsUseCase(uow, FakeOutboxReader()).execute(uuid.uuid4())


def _queues(dlq_messages):
    admin = FakeQueueAdmin({"payments.new": [], "payments.dlq": dlq_messages, "other": []})
    publisher = FakePublisher()
    return QueueAdminUseCase(admin, publisher, dlq_name="payments.dlq"), admin, publisher


async def test_requeue_moves_messages_from_dlq_to_main():
    use_case, admin, publisher = _queues(
        [{"payload": '{"payment_id": "a"}'}, {"payload": "not json"}, {"payload": '{"payment_id": "c"}'}]
    )

    moved = await use_case.requeue("payments.dlq", 2)

    assert moved == 2
    assert [p for p, _ in publisher.published] == [{"payment_id": "a"}, {"raw": "not json"}]
    assert publisher.published[0][1] == {"x-requeued-from": "payments.dlq", "x-attempt": 1}
    assert len(admin.queues["payments.dlq"]) == 1


async def test_requeue_only_from_dlq_and_only_service_queues():
    use_case, _, _ = _queues([])
    with pytest.raises(RequeueNotAllowedError):
        await use_case.requeue("payments.new", 1)
    with pytest.raises(UnknownQueueError):
        await use_case.requeue("other", 1)
    with pytest.raises(UnknownQueueError):
        await use_case.purge("../api/users")


async def test_list_queues_only_service_ones_sorted():
    use_case, _, _ = _queues([])
    assert [q["name"] for q in await use_case.list_queues()] == ["payments.dlq", "payments.new"]
