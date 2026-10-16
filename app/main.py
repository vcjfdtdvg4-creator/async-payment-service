import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.outbox import run_relay
from app.ui import router as ui_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    relay = asyncio.create_task(run_relay(stop))
    try:
        yield
    finally:
        stop.set()
        await relay


app = FastAPI(
    title="Async Payment Processing Service",
    lifespan=lifespan,
    description="JSON API + встроенная админка: **/ui/**",
)

app.include_router(api_router)  # JSON API под X-API-Key
app.include_router(ui_router)   # админка под cookie-сессией
app.mount("/ui/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="ui-static")


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/ui/")
