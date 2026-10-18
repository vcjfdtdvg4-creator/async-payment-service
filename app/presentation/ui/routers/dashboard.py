from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from app.application.admin.list_payments import ListPaymentsQuery, ListPaymentsUseCase
from app.config import settings
from app.domain.payments.values import Status
from app.presentation.ui.auth import require_session
from app.presentation.ui.deps import get_list_payments_use_case
from app.presentation.ui.templating import render

router = APIRouter(dependencies=[Depends(require_session)])


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    page: int = Query(1, ge=1),
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None),
    use_case: ListPaymentsUseCase = Depends(get_list_payments_use_case),
) -> Response:
    status = Status(status_filter) if status_filter in {s.value for s in Status} else None
    result = await use_case.execute(
        ListPaymentsQuery(page=page, page_size=settings.ui_page_size, status=status, search=q or None)
    )
    qs = {k: v for k, v in (("status", status.value if status else None), ("q", q)) if v}
    return render(
        request,
        "dashboard.html",
        {
            "payments": result.items,
            "total": result.total,
            "page": result.page,
            "total_pages": result.total_pages,
            "status_filter": status.value if status else "",
            "q": q or "",
            "stats": {s.value: n for s, n in result.stats.items()},
            "qs": urlencode(qs),
        },
    )
