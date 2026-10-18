from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

UI_DIR = Path(__file__).parent
STATIC_DIR = UI_DIR / "static"

templates = Jinja2Templates(directory=str(UI_DIR / "templates"))


def render(request: Request, name: str, ctx: dict[str, Any] | None = None, status_code: int = 200) -> Response:
    return templates.TemplateResponse(request, name, ctx or {}, status_code=status_code)
