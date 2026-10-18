from decimal import Decimal

import pytest

from app.domain.payments.events import PaymentCreated
from app.domain.payments.values import Currency, Status


def test_create_sets_pending_and_emits_event(make_payment):
    p = make_payment()
    assert p.status is Status.pending
    assert not p.is_final
    assert not p.is_webhook_delivered
    assert p.pull_events() == [PaymentCreated(payment_id=p.id)]
    assert p.pull_events() == []


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1")])
def test_amount_must_be_positive(make_payment, amount):
    with pytest.raises(ValueError):
        make_payment(amount=amount)


@pytest.mark.parametrize("status", [Status.succeeded, Status.failed])
def test_final_statuses(make_payment, status):
    p = make_payment()
    p.status = status
    assert p.is_final


def test_matches_compares_request_body(make_payment):
    p = make_payment()
    same = dict(
        amount=Decimal("100.00"), currency=Currency.RUB, description="Order #1",
        webhook_url="https://example.com/hook", meta={"order_id": 1},
    )
    assert p.matches(**same)
    assert not p.matches(**{**same, "amount": Decimal("101")})
    assert not p.matches(**{**same, "currency": Currency.USD})
    assert not p.matches(**{**same, "meta": {}})
