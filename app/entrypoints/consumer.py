import httpx
from faststream import ContextRepo, FastStream

from app.config import settings
from app.infrastructure.broker.connection import broker
from app.infrastructure.broker.topology import declare_topology
from app.infrastructure.db.session import engine
from app.infrastructure.logs import setup_logging
from app.presentation.consumer.handlers.payments import router as payments_router

setup_logging()

broker.include_router(payments_router)

app = FastStream(broker)


@app.on_startup
async def setup(context: ContextRepo) -> None:
    context.set_global("http_client", httpx.AsyncClient(timeout=settings.webhook_timeout_seconds))


@app.after_startup
async def declare() -> None:
    await declare_topology(broker)


@app.after_shutdown
async def teardown(context: ContextRepo) -> None:
    await context.get("http_client").aclose()
    await engine.dispose()
