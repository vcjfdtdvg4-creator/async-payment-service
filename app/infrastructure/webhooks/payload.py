from typing import Any

from app.domain.payments.entity import Payment


def build_webhook_payload(p: Payment) -> dict[str, Any]:
    return {
        "payment_id": str(p.id),
        "status": p.status.value,
        "amount": str(p.amount),
        "currency": p.currency.value,
        "description": p.description,
        "metadata": p.meta,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "processed_at": p.processed_at.isoformat() if p.processed_at else None,
    }
