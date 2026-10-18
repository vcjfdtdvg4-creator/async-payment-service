import json
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from starlette.responses import Response

from app.application.admin.payment_details import GetPaymentDetailsUseCase
from app.application.payments.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.domain.payments.exceptions import IdempotencyConflictError, PaymentNotFoundError
from app.infrastructure.webhooks.payload import build_webhook_payload
from app.presentation.api.schemas.payments import CreatePaymentRequest
from app.presentation.ui.auth import require_session
from app.presentation.ui.deps import get_create_payment_use_case, get_payment_details_use_case
from app.presentation.ui.templating import render

router = APIRouter(prefix="/payments", dependencies=[Depends(require_session)])


@router.get("/new", response_class=HTMLResponse)
async def new_payment_form(request: Request) -> Response:
    return render(
        request,
        "payment_new.html",
        {"default_key": f"ui-{uuid.uuid4().hex[:12]}", "errors": None, "values": {}},
    )


@router.post("/new")
async def new_payment_submit(
    request: Request,
    amount: str = Form(...),
    currency: str = Form(...),
    description: str = Form(...),
    metadata: str = Form(""),
    webhook_url: str = Form(...),
    idempotency_key: str = Form(...),
    use_case: CreatePaymentUseCase = Depends(get_create_payment_use_case),
) -> Response:
    values = {
        "amount": amount, "currency": currency, "description": description,
        "metadata": metadata, "webhook_url": webhook_url, "idempotency_key": idempotency_key,
    }

    def fail(errors: list[str]) -> Response:
        return render(
            request, "payment_new.html",
            {"default_key": idempotency_key, "errors": errors, "values": values}, 400,
        )

    try:
        meta_obj = json.loads(metadata) if metadata.strip() else {}
        if not isinstance(meta_obj, dict):
            raise ValueError("must be a JSON object")
    except ValueError as exc:  # JSONDecodeError наследует ValueError
        return fail([f"metadata: {exc}"])

    if not 1 <= len(idempotency_key) <= 255:
        return fail(["idempotency_key: length must be 1..255"])

    try:
        body = CreatePaymentRequest(
            amount=amount, currency=currency, description=description,
            metadata=meta_obj, webhook_url=webhook_url,
        )
    except ValidationError as exc:
        return fail([f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()])

    try:
        result = await use_case.execute(
            CreatePaymentCommand(
                amount=body.amount,
                currency=body.currency,
                description=body.description,
                metadata=body.metadata,
                webhook_url=str(body.webhook_url),
                idempotency_key=idempotency_key,
            )
        )
    except IdempotencyConflictError as exc:
        return fail([f"idempotency_key: {exc}"])
    return RedirectResponse(f"/ui/payments/{result.payment_id}", status_code=303)


@router.get("/{payment_id}", response_class=HTMLResponse)
async def payment_detail(
    request: Request,
    payment_id: uuid.UUID,
    use_case: GetPaymentDetailsUseCase = Depends(get_payment_details_use_case),
) -> Response:
    try:
        details = await use_case.execute(payment_id)
    except PaymentNotFoundError:
        return render(request, "not_found.html", status_code=404)
    return render(
        request,
        "payment_detail.html",
        {
            "p": details.payment,
            "events": details.events,
            "webhook_payload": json.dumps(build_webhook_payload(details.payment), indent=2, ensure_ascii=False),
        },
    )
