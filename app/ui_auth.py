"""Простая cookie-сессия для админки.

Токены хранятся в памяти процесса api; рестарт сбрасывает сессии. Сам API-ключ в cookie не уходит.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Cookie, HTTPException, status

_sessions: set[str] = set()


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions.add(token)
    return token


def drop_session(token: str | None) -> None:
    if token:
        _sessions.discard(token)


async def require_session(ui_session: Annotated[str | None, Cookie()] = None) -> str:
    if not ui_session or ui_session not in _sessions:
        # 303 + Location -> браузер сам уйдёт на форму логина
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/ui/login"})
    return ui_session
