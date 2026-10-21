from faststream import FastStream

from app.config import settings
from app.infrastructure.broker.connection import broker
from app.infrastructure.broker.topology import declare_topology
from app.infrastructure.db.session import engine, session_factory
from app.infrastructure.logs import setup_logging
from app.infrastructure.outbox.relay import OutboxRelay

setup_logging()

app = FastStream(broker)
relay = OutboxRelay(
    session_factory=session_factory,
    broker=broker,
    batch_size=settings.outbox_batch_size,
    poll_interval=settings.outbox_poll_interval_seconds,
)


@app.after_startup
async def start() -> None:
    await declare_topology(broker)
    relay.start()


@app.on_shutdown
async def stop() -> None:
    await relay.stop()
    await engine.dispose()
