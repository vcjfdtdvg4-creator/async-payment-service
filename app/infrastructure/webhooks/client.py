import httpx

from app.domain.payments.entity import Payment
from app.infrastructure.webhooks.payload import build_webhook_payload


class HttpWebhookNotifier:
    """POST JSON на webhook_url. Бросает исключение при сетевой ошибке или не-2xx ответе.

    Повторные попытки выполняются не здесь, а на уровне consumer'а через retry-очереди.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def notify(self, payment: Payment) -> None:
        resp = await self._client.post(
            payment.webhook_url,
            json=build_webhook_payload(payment),
            headers={"X-Payment-Event": "payment.processed"},
        )
        resp.raise_for_status()
