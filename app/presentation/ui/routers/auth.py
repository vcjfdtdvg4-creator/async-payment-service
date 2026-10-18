import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.config import settings
from app.presentation.ui.auth import SESSION_COOKIE, create_session, drop_session
from app.presentation.ui.templating import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    return render(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, api_key: str = Form(...)) -> Response:
    if not secrets.compare_digest(api_key, settings.api_key):
        return render(request, "login.html", {"error": "Invalid API key"}, 401)
    resp = RedirectResponse("/ui/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, create_session(), httponly=True, samesite="lax", max_age=24 * 3600)
    return resp


@router.get("/logout")
async def logout(request: Request) -> Response:
    drop_session(request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse("/ui/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
