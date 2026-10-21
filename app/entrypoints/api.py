from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.infrastructure.db.session import engine
from app.infrastructure.logs import setup_logging
from app.presentation.api.errors import register_exception_handlers
from app.presentation.api.routers.payments import router as payments_router
from app.presentation.api.routers.system import router as system_router
from app.presentation.ui.router import router as ui_router
from app.presentation.ui.templating import STATIC_DIR


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="Async Payment Processing Service",
        version="1.0.0",
        description="JSON API + встроенная админка: **/ui/**",
        lifespan=lifespan,
    )
    app.include_router(payments_router)
    app.include_router(ui_router)
    app.include_router(system_router)
    app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui-static")

    register_exception_handlers(app)
    return app


app = create_app()
