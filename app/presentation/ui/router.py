from fastapi import APIRouter

from app.presentation.ui.routers import auth, dashboard, outbox, payments, queues

router = APIRouter(prefix="/ui", tags=["UI"], include_in_schema=False)
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(payments.router)
router.include_router(outbox.router)
router.include_router(queues.router)
