from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from app.application.admin.payment_details import ListOutboxUseCase
from app.presentation.ui.auth import require_session
from app.presentation.ui.deps import get_list_outbox_use_case
from app.presentation.ui.templating import render

router = APIRouter(dependencies=[Depends(require_session)])


@router.get("/outbox", response_class=HTMLResponse)
async def outbox_view(request: Request, use_case: ListOutboxUseCase = Depends(get_list_outbox_use_case)) -> Response:
    return render(request, "outbox.html", {"events": await use_case.execute()})
