"""
Проверка подписи initData, которую Telegram передаёт в Mini App.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE = 24 * 60 * 60  # initData старше суток не принимаем


class AuthError(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int = MAX_AGE) -> dict:
    """
    Проверяет подпись и возвращает данные пользователя Telegram (dict с id, username, first_name...).
    Бросает AuthError, если подпись неверна или данные устарели.
    """
    if not init_data:
        raise AuthError("no init data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise AuthError("no hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise AuthError("bad signature")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise AuthError("bad auth_date")
    if time.time() - auth_date > max_age:
        raise AuthError("init data expired")

    try:
        user = json.loads(pairs.get("user", "{}"))
    except ValueError:
        raise AuthError("bad user")
    if not isinstance(user, dict) or "id" not in user:
        raise AuthError("no user")
    return user


def sign_init_data(fields: dict, bot_token: str) -> str:
    """Создаёт подписанную initData (для тестов)."""
    from urllib.parse import urlencode
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})
