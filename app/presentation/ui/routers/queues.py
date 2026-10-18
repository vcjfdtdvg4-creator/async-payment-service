import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.application.admin.queues import QueueAdminUseCase, RequeueNotAllowedError, UnknownQueueError
from app.presentation.ui.auth import require_session
from app.presentation.ui.deps import get_queue_admin_use_case
from app.presentation.ui.templating import render

router = APIRouter(prefix="/queues", dependencies=[Depends(require_session)])

QueueAdminDep = Depends(get_queue_admin_use_case)


@router.get("", response_class=HTMLResponse)
async def queues_view(request: Request, use_case: QueueAdminUseCase = QueueAdminDep) -> Response:
    try:
        queues, error = await use_case.list_queues(), None
    except httpx.HTTPError as exc:
        queues, error = [], str(exc)
    return render(request, "queues.html", {"queues": queues, "error": error, "dlq_name": use_case.dlq_name})


@router.get("/{queue_name}", response_class=HTMLResponse)
async def queue_detail(request: Request, queue_name: str, use_case: QueueAdminUseCase = QueueAdminDep) -> Response:
    ctx = {"queue_name": queue_name, "is_dlq": queue_name == use_case.dlq_name, "info": None, "messages": [], "error": None}
    try:
        snapshot = await use_case.snapshot(queue_name)
    except UnknownQueueError:
        raise HTTPException(404, "Unknown queue")
    except httpx.HTTPError as exc:
        ctx["error"] = str(exc)
        return render(request, "queue_detail.html", ctx, 502)
    ctx.update(info=snapshot.info, messages=snapshot.messages)
    return render(request, "queue_detail.html", ctx)


async def _requeue(use_case: QueueAdminUseCase, queue_name: str, count: int) -> RedirectResponse:
    try:
        await use_case.requeue(queue_name, count)
    except UnknownQueueError:
        raise HTTPException(404, "Unknown queue")
    except RequeueNotAllowedError:
        raise HTTPException(400, "Requeue is allowed only for the DLQ")
    return RedirectResponse(f"/ui/queues/{queue_name}", status_code=303)


@router.post("/{queue_name}/requeue-one")
async def queue_requeue_one(queue_name: str, use_case: QueueAdminUseCase = QueueAdminDep) -> RedirectResponse:
    return await _requeue(use_case, queue_name, 1)


@router.post("/{queue_name}/requeue-all")
async def queue_requeue_all(queue_name: str, use_case: QueueAdminUseCase = QueueAdminDep) -> RedirectResponse:
    return await _requeue(use_case, queue_name, 500)


@router.post("/{queue_name}/purge")
async def queue_purge(queue_name: str, use_case: QueueAdminUseCase = QueueAdminDep) -> RedirectResponse:
    try:
        await use_case.purge(queue_name)
    except UnknownQueueError:
        raise HTTPException(404, "Unknown queue")
    return RedirectResponse(f"/ui/queues/{queue_name}", status_code=303)
