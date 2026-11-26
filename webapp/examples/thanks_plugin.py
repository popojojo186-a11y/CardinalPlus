"""
Пример плагина Cardinal Plus с интерфейсом в Mini App.

Скопируйте thanks_plugin.py и thanks_plugin.html в папку plugins/ и перезапустите Cardinal.
В обычном Cardinal (без Mini App) плагин тоже загрузится — просто без интерфейса.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

try:
    from webapp.plugin_api import settings
except ImportError:  # запущено в обычном Cardinal без Mini App
    settings = None

NAME = "Спасибо за покупку"
VERSION = "1.0.0"
DESCRIPTION = "Пишет покупателю сообщение после нового заказа. Пример плагина с интерфейсом."
CREDITS = "Cardinal Plus"
UUID = "6c2b5f1e-8a3d-4c7b-9e21-3f5a7d9b1c42"
SETTINGS_PAGE = False

DEFAULTS = {"enabled": True, "text": "Спасибо за покупку, $username! Если будут вопросы — пишите.", "delay": 3}

stats = {"sent": 0, "last": None}


def cfg(key):
    if settings is None:
        return DEFAULTS[key]
    return settings(UUID).get(key)


def on_new_order(cardinal: Cardinal, event):
    if not cfg("enabled"):
        return
    order = event.order
    text = str(cfg("text")).replace("$username", order.buyer_username).replace("$order_id", order.id)
    time.sleep(max(0, float(cfg("delay") or 0)))
    cardinal.send_message(order.chat_id, text, order.buyer_username)
    stats["sent"] += 1
    stats["last"] = {"buyer": order.buyer_username, "order": order.id, "time": int(time.time())}


# ---------- методы для страницы плагина ----------
def api_stats(cardinal: Cardinal, data: dict):
    return stats


def api_reset(cardinal: Cardinal, data: dict):
    stats["sent"] = 0
    stats["last"] = None
    return stats


# ---------- описание интерфейса ----------
WEBAPP = {
    "icon": "💌",
    "settings": [
        {"key": "enabled", "type": "toggle", "label": "Отправлять сообщение", "default": DEFAULTS["enabled"]},
        {"key": "text", "type": "textarea", "label": "Текст сообщения", "default": DEFAULTS["text"],
         "hint": "$username — ник покупателя, $order_id — номер заказа"},
        {"key": "delay", "type": "number", "label": "Задержка, сек", "default": DEFAULTS["delay"], "min": 0, "max": 60},
    ],
    "page": "thanks_plugin.html",
    "routes": {"stats": api_stats, "reset": api_reset},
}

BIND_TO_NEW_ORDER = [on_new_order]
BIND_TO_DELETE = None
