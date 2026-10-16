"""Server-rendered admin UI. Ходит в ту же БД и в RabbitMQ Management API."""
from __future__ import annotations

import json
import re
import secrets
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from faststream.rabbit import RabbitBroker
from pydantic import ValidationError
from sqlalchemy import desc, func, or_, select

from app.config import settings
from app.db import SessionLocal
from app.messaging import DLQ_NAME, EXCHANGE, ROUTING_KEY
from app.models import OutboxEvent, Payment, PaymentStatus
from app.schemas import PaymentCreate
from app.services import create_payment as create_payment_record
from app.services import find_by_idempotency_key
from app.ui_auth import create_session, drop_session, require_session
from app.webhook import build_payload

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(prefix="/ui", tags=["UI"], include_in_schema=False)
SessionToken = Depends(require_session)

_QUEUE_RE = re.compile(r"^payments\.[A-Za-z0-9._-]+$")


def _render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(request, name, ctx or {}, status_code=status_code)


def _check_queue(name: str) -> str:
    """Админка работает только с очередями сервиса."""
    if not _QUEUE_RE.match(name):
        raise HTTPException(404, "Unknown queue")
    return name


# --------------------------------------------------------------------------- #
# RabbitMQ Management API
# --------------------------------------------------------------------------- #
def _rmq_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.rabbitmq_management_url,
        auth=(settings.rabbitmq_management_user, settings.rabbitmq_management_password),
        timeout=10.0,
    )


async def _rmq_get(path: str) -> Any:
    async with _rmq_client() as c:
        r = await c.get(path)
        r.raise_for_status()
        return r.json()


async def _rmq_post(path: str, body: dict) -> Any:
    async with _rmq_client() as c:
        r = await c.post(path, json=body)
        r.raise_for_status()
        return r.json() if r.content else None


async def _rmq_delete(path: str) -> None:
    async with _rmq_client() as c:
        r = await c.delete(path)
        r.raise_for_status()


async def _list_queues() -> list[dict]:
    return [q for q in await _rmq_get("/api/queues/%2F") if q.get("name", "").startswith("payments.")]


async def _get_messages(queue: str, count: int, requeue: bool) -> list[dict]:
    return await _rmq_post(
        f"/api/queues/%2F/{queue}/get",
        {
            "count": count,
            "ackmode": "ack_requeue_true" if requeue else "ack_requeue_false",
            "encoding": "auto",
            "truncate": 50000,
        },
    )


async def _republish_to_main(messages: list[dict], source: str) -> None:
    """Публикует вынутые сообщения обратно в payments.new (x-attempt=1)."""
    if not messages:
        return
    broker = RabbitBroker(settings.rabbitmq_url)
    await broker.start()
    try:
        for m in messages:
            payload = m.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"raw": payload}
            await broker.publish(
                payload,
                exchange=EXCHANGE,
                routing_key=ROUTING_KEY,
                persist=True,
                headers={"x-requeued-from": source, "x-attempt": 1},
            )
    finally:
        await broker.close()


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return _render(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, api_key: str = Form(...)):
    if not secrets.compare_digest(api_key, settings.api_key):
        return _render(request, "login.html", {"error": "Invalid API key"}, 401)
    resp = RedirectResponse("/ui/", status_code=303)
    resp.set_cookie("ui_session", create_session(), httponly=True, samesite="lax", max_age=24 * 3600)
    return resp


@router.get("/logout")
async def logout(request: Request):
    drop_session(request.cookies.get("ui_session"))
    resp = RedirectResponse("/ui/login", status_code=303)
    resp.delete_cookie("ui_session")
    return resp


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _token: str = SessionToken,
    page: int = Query(1, ge=1),
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None),
):
    size = settings.ui_page_size
    async with SessionLocal() as session:
        stmt = select(Payment)
        count_stmt = select(func.count()).select_from(Payment)
        if status_filter in {s.value for s in PaymentStatus}:
            stmt = stmt.where(Payment.status == status_filter)
            count_stmt = count_stmt.where(Payment.status == status_filter)
        else:
            status_filter = None
        if q:
            like = f"%{q}%"
            cond = or_(Payment.description.ilike(like), Payment.idempotency_key.ilike(like))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        items = list(
            (await session.execute(stmt.order_by(desc(Payment.created_at)).offset((page - 1) * size).limit(size)))
            .scalars()
            .all()
        )
        total = int((await session.execute(count_stmt)).scalar_one())
        rows = (await session.execute(select(Payment.status, func.count()).group_by(Payment.status))).all()

    stats = {s.value: 0 for s in PaymentStatus}
    for st, cnt in rows:
        stats[st] = cnt
    qs = {k: v for k, v in (("status", status_filter), ("q", q)) if v}
    return _render(
        request,
        "dashboard.html",
        {
            "payments": items,
            "total": total,
            "page": page,
            "total_pages": max(1, (total + size - 1) // size),
            "status_filter": status_filter or "",
            "q": q or "",
            "stats": stats,
            "qs": urlencode(qs),
        },
    )


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
@router.get("/payments/new", response_class=HTMLResponse)
async def new_payment_form(request: Request, _token: str = SessionToken):
    return _render(
        request,
        "payment_new.html",
        {"default_key": f"ui-{uuid.uuid4().hex[:12]}", "errors": None, "values": {}},
    )


@router.post("/payments/new")
async def new_payment_submit(
    request: Request,
    _token: str = SessionToken,
    amount: str = Form(...),
    currency: str = Form(...),
    description: str = Form(...),
    metadata: str = Form(""),
    webhook_url: str = Form(...),
    idempotency_key: str = Form(...),
):
    values = {
        "amount": amount, "currency": currency, "description": description,
        "metadata": metadata, "webhook_url": webhook_url, "idempotency_key": idempotency_key,
    }

    def fail(errors: list[str]):
        return _render(
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
        body = PaymentCreate(
            amount=amount, currency=currency, description=description,
            metadata=meta_obj, webhook_url=webhook_url,
        )
    except ValidationError as exc:
        return fail([f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()])

    async with SessionLocal() as session:
        payment = await create_payment_record(session, body, idempotency_key)
    return RedirectResponse(f"/ui/payments/{payment.id}", status_code=303)


# --------------------------------------------------------------------------- #
# detail / outbox
# --------------------------------------------------------------------------- #
@router.get("/payments/{payment_id}", response_class=HTMLResponse)
async def payment_detail(request: Request, payment_id: uuid.UUID, _token: str = SessionToken):
    async with SessionLocal() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return _render(request, "not_found.html", status_code=404)
        events = list(
            (
                await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.payload["payment_id"].astext == str(payment_id))
                    .order_by(desc(OutboxEvent.created_at))
                )
            ).scalars().all()
        )
    return _render(
        request,
        "payment_detail.html",
        {
            "p": payment,
            "events": events,
            "webhook_payload": json.dumps(build_payload(payment), indent=2, ensure_ascii=False),
        },
    )


@router.get("/outbox", response_class=HTMLResponse)
async def outbox_view(request: Request, _token: str = SessionToken):
    async with SessionLocal() as session:
        events = list(
            (await session.execute(select(OutboxEvent).order_by(desc(OutboxEvent.created_at)).limit(100)))
            .scalars().all()
        )
    return _render(request, "outbox.html", {"events": events})


# --------------------------------------------------------------------------- #
# queues
# --------------------------------------------------------------------------- #
@router.get("/queues", response_class=HTMLResponse)
async def queues_view(request: Request, _token: str = SessionToken):
    try:
        queues, error = await _list_queues(), None
    except httpx.HTTPError as exc:
        queues, error = [], str(exc)
    queues.sort(key=lambda q: q["name"])
    return _render(request, "queues.html", {"queues": queues, "error": error, "dlq_name": DLQ_NAME})


@router.get("/queues/{queue_name}", response_class=HTMLResponse)
async def queue_detail(request: Request, queue_name: str, _token: str = SessionToken):
    _check_queue(queue_name)
    ctx = {"queue_name": queue_name, "is_dlq": queue_name == DLQ_NAME, "info": None, "messages": [], "error": None}
    try:
        ctx["info"] = await _rmq_get(f"/api/queues/%2F/{queue_name}")
        ctx["messages"] = await _get_messages(queue_name, 20, requeue=True)  # не destructive
    except httpx.HTTPError as exc:
        ctx["error"] = str(exc)
        return _render(request, "queue_detail.html", ctx, 502)
    return _render(request, "queue_detail.html", ctx)


async def _requeue(queue_name: str, count: int) -> RedirectResponse:
    _check_queue(queue_name)
    if queue_name != DLQ_NAME:
        raise HTTPException(400, "Requeue is allowed only for the DLQ")
    msgs = await _get_messages(queue_name, count, requeue=False)
    await _republish_to_main(msgs, queue_name)
    return RedirectResponse(f"/ui/queues/{queue_name}", status_code=303)


@router.post("/queues/{queue_name}/requeue-one")
async def queue_requeue_one(queue_name: str, _token: str = SessionToken):
    return await _requeue(queue_name, 1)


@router.post("/queues/{queue_name}/requeue-all")
async def queue_requeue_all(queue_name: str, _token: str = SessionToken):
    return await _requeue(queue_name, 500)


@router.post("/queues/{queue_name}/purge")
async def queue_purge(queue_name: str, _token: str = SessionToken):
    _check_queue(queue_name)
    await _rmq_delete(f"/api/queues/%2F/{queue_name}/contents")
    return RedirectResponse(f"/ui/queues/{queue_name}", status_code=303)
