import httpx

from app.config import settings
from app.models import Payment


def build_payload(p: Payment) -> dict:
    return {
        "payment_id": str(p.id),
        "status": p.status,
        "amount": str(p.amount),
        "currency": p.currency,
        "description": p.description,
        "metadata": p.meta,
        "created_at": p.created_at.isoformat(),
        "processed_at": p.processed_at.isoformat() if p.processed_at else None,
    }


async def send_webhook(p: Payment) -> None:
    """Бросает исключение при сетевой ошибке или не-2xx ответе.

    Повторные попытки выполняются не здесь, а на уровне consumer'а через retry-очереди.
    """
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        resp = await client.post(p.webhook_url, json=build_payload(p), headers={"X-Payment-Event": "payment.processed"})
        resp.raise_for_status()
