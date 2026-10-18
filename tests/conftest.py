import os
from decimal import Decimal

import pytest

# Настройки для тестов: без .env и без реальных сервисов.
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

from app.domain.payments.entity import Payment  # noqa: E402
from app.domain.payments.values import Currency  # noqa: E402


@pytest.fixture
def make_payment():
    def _make(**overrides) -> Payment:
        data = dict(
            amount=Decimal("100.00"),
            currency=Currency.RUB,
            description="Order #1",
            idempotency_key="key-1",
            webhook_url="https://example.com/hook",
            meta={"order_id": 1},
        )
        data.update(overrides)
        return Payment.create(**data)

    return _make
