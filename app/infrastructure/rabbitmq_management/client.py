from typing import Any
from urllib.parse import quote

import httpx

_VHOST = "%2F"


class RabbitManagementQueueAdmin:
    def __init__(self, base_url: str, user: str, password: str, timeout: float = 10.0) -> None:
        self._base_url = base_url
        self._auth = (user, password)
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, auth=self._auth, timeout=self._timeout)

    async def list_queues(self, prefix: str) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get(f"/api/queues/{_VHOST}")
            r.raise_for_status()
            return [q for q in r.json() if q.get("name", "").startswith(prefix)]

    async def get_queue(self, name: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/api/queues/{_VHOST}/{quote(name)}")
            r.raise_for_status()
            return r.json()

    async def peek(self, name: str, count: int) -> list[dict[str, Any]]:
        return await self._get_messages(name, count, requeue=True)

    async def take(self, name: str, count: int) -> list[dict[str, Any]]:
        return await self._get_messages(name, count, requeue=False)

    async def purge(self, name: str) -> None:
        async with self._client() as c:
            r = await c.delete(f"/api/queues/{_VHOST}/{quote(name)}/contents")
            r.raise_for_status()

    async def _get_messages(self, name: str, count: int, requeue: bool) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.post(
                f"/api/queues/{_VHOST}/{quote(name)}/get",
                json={
                    "count": count,
                    "ackmode": "ack_requeue_true" if requeue else "ack_requeue_false",
                    "encoding": "auto",
                    "truncate": 50000,
                },
            )
            r.raise_for_status()
            return r.json() if r.content else []
