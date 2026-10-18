import pytest
from fastapi.testclient import TestClient

from app.application.payments.create_payment import CreatePaymentUseCase
from app.application.payments.get_payment import GetPaymentUseCase
from app.entrypoints.api import app
from app.presentation.api.deps.payments import get_create_payment_use_case, get_get_payment_use_case
from tests.fakes import FakeUnitOfWork

HEADERS = {"X-API-Key": "test-key"}
BODY = {
    "amount": "1500.00",
    "currency": "RUB",
    "description": "Order #1001",
    "metadata": {"order_id": 1001},
    "webhook_url": "https://example.com/hook",
}


@pytest.fixture
def client():
    uow = FakeUnitOfWork()
    app.dependency_overrides[get_create_payment_use_case] = lambda: CreatePaymentUseCase(uow)
    app.dependency_overrides[get_get_payment_use_case] = lambda: GetPaymentUseCase(uow)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create(client, key="order-1001", body=BODY):
    return client.post("/api/v1/payments", json=body, headers={**HEADERS, "Idempotency-Key": key})


def test_create_and_get(client):
    resp = _create(client)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"

    got = client.get(f"/api/v1/payments/{data['payment_id']}", headers=HEADERS)
    assert got.status_code == 200
    assert got.json()["metadata"] == {"order_id": 1001}
    assert got.json()["amount"] == "1500.00"


def test_idempotent_replay_and_conflict(client):
    first = _create(client).json()
    assert _create(client).json()["payment_id"] == first["payment_id"]
    conflict = _create(client, body={**BODY, "amount": "1.00"})
    assert conflict.status_code == 409


def test_auth_and_validation(client):
    assert client.post("/api/v1/payments", json=BODY, headers={"Idempotency-Key": "k"}).status_code == 401
    assert client.post("/api/v1/payments", json=BODY, headers=HEADERS).status_code == 422
    assert _create(client, body={**BODY, "currency": "GBP"}).status_code == 422
    assert _create(client, body={**BODY, "amount": "-5"}).status_code == 422


def test_not_found(client):
    resp = client.get("/api/v1/payments/00000000-0000-0000-0000-000000000000", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Payment not found"}


def test_health_and_ui_redirects_to_login(client):
    assert client.get("/health").json() == {"status": "ok"}
    resp = client.get("/ui/", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/ui/login"
