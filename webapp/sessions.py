"""
Вход в приложение из обычного браузера (режим «Панель»).

1. Пользователь пишет боту /web (или нажимает «Открыть в браузере» в Mini App).
2. Бот выдаёт одноразовую ссылку …/login?t=<токен>, действующую 5 минут.
3. По ссылке сервер ставит cookie-сессию на 30 дней.

В файле хранятся только SHA-256 хэши токенов, сами токены нигде не сохраняются.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time

SESSIONS_PATH = "storage/cache/webapp_sessions.json"
LOGIN_TTL = 5 * 60
SESSION_TTL = 30 * 24 * 60 * 60
COOKIE_NAME = "cp_session"

_lock = threading.RLock()
_login_tokens: dict[str, tuple[int, float]] = {}   # hash -> (user_id, expires)
_sessions: dict[str, dict] | None = None           # hash -> {"user_id", "expires", "name"}


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> dict:
    global _sessions
    if _sessions is None:
        _sessions = {}
        if os.path.exists(SESSIONS_PATH):
            try:
                with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
                    _sessions = json.load(f)
            except (OSError, ValueError):
                _sessions = {}
    return _sessions


def _save():
    os.makedirs(os.path.dirname(SESSIONS_PATH), exist_ok=True)
    tmp = SESSIONS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_sessions or {}, f)
    os.replace(tmp, SESSIONS_PATH)


def create_login_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        for k in [k for k, (_, exp) in _login_tokens.items() if exp < now]:
            _login_tokens.pop(k, None)
        _login_tokens[_h(token)] = (user_id, now + LOGIN_TTL)
    return token


def redeem_login_token(token: str, name: str = "") -> tuple[str, int] | None:
    """Обменивает одноразовый токен на сессию. Возвращает (session_token, user_id) или None."""
    with _lock:
        item = _login_tokens.pop(_h(token or ""), None)
        if not item or item[1] < time.time():
            return None
        user_id = item[0]
        session = secrets.token_urlsafe(32)
        sessions = _load()
        now = time.time()
        for k in [k for k, v in sessions.items() if v.get("expires", 0) < now]:
            sessions.pop(k, None)
        sessions[_h(session)] = {"user_id": user_id, "expires": now + SESSION_TTL, "name": name}
        _save()
        return session, user_id


def get_session_user(session: str) -> int | None:
    if not session:
        return None
    with _lock:
        item = _load().get(_h(session))
        if not item or item.get("expires", 0) < time.time():
            return None
        return int(item["user_id"])


def delete_session(session: str) -> None:
    with _lock:
        if _load().pop(_h(session or ""), None) is not None:
            _save()
