from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.payments.exceptions import IdempotencyConflictError, PaymentNotFoundError


async def _not_found(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Payment not found"}, status_code=status.HTTP_404_NOT_FOUND)


async def _conflict(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentNotFoundError, _not_found)
    app.add_exception_handler(IdempotencyConflictError, _conflict)
