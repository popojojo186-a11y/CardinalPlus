"""
API для плагинов с интерфейсом в Mini App.

Обычные плагины Cardinal работают без изменений. Чтобы у плагина появился интерфейс в приложении,
достаточно добавить в него словарь WEBAPP (см. webapp/PLUGINS.md):

    from webapp.plugin_api import settings

    WEBAPP = {
        "icon": "🎁",
        "settings": [
            {"key": "enabled", "type": "toggle", "label": "Включить бонус", "default": True},
        ],
    }

    def on_new_order(cardinal, event):
        if settings(UUID).get("enabled"):
            ...
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger("FPC.webapp")

STORAGE_DIR = "storage/webapp_plugins"
FIELD_TYPES = {"toggle", "text", "textarea", "number", "select"}

_lock = threading.RLock()
_cache: dict[str, "PluginSettings"] = {}


class PluginSettings:
    """Настройки одного плагина. Хранятся в storage/webapp_plugins/<uuid>.json."""

    def __init__(self, uuid: str, schema: list[dict] | None = None):
        self.uuid = uuid
        self.schema = schema or []
        self.path = os.path.join(STORAGE_DIR, f"{uuid}.json")
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (OSError, ValueError):
                logger.warning(f"Не удалось прочитать {self.path}, использую значения по умолчанию.")
                self._data = {}

    def _save(self):
        os.makedirs(STORAGE_DIR, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=4)
        os.replace(tmp, self.path)

    def _default(self, key: str):
        for field in self.schema:
            if field.get("key") == key:
                return field.get("default")
        return None

    def get(self, key: str, default: Any = None) -> Any:
        with _lock:
            if key in self._data:
                return self._data[key]
        value = self._default(key)
        return default if value is None else value

    def set(self, key: str, value: Any) -> None:
        with _lock:
            self._data[key] = value
            self._save()

    def all(self) -> dict[str, Any]:
        result = {f["key"]: self.get(f["key"]) for f in self.schema if "key" in f}
        with _lock:
            result.update({k: v for k, v in self._data.items() if k not in result})
        return result

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)


def settings(uuid: str) -> PluginSettings:
    """Возвращает объект настроек плагина. Можно вызывать в любом месте плагина."""
    with _lock:
        if uuid not in _cache:
            _cache[uuid] = PluginSettings(uuid)
        return _cache[uuid]


def get_webapp_spec(plugin_module) -> dict | None:
    spec = getattr(plugin_module, "WEBAPP", None)
    return spec if isinstance(spec, dict) else None


def has_page(spec: dict) -> bool:
    """Страница плагина: файл рядом с плагином (page) или HTML прямо в коде (page_html)."""
    return bool(spec.get("page") or isinstance(spec.get("page_html"), str))


def bind_schema(uuid: str, schema: list[dict]) -> PluginSettings:
    s = settings(uuid)
    s.schema = schema
    return s


def coerce_value(field: dict, value: Any) -> Any:
    """Приводит значение из приложения к типу поля и проверяет ограничения."""
    t = field.get("type")
    if t == "toggle":
        return bool(value)
    if t in ("text", "textarea"):
        value = "" if value is None else str(value)
        max_len = field.get("max_length", 4000)
        if len(value) > max_len:
            raise ValueError(f"Слишком длинный текст (максимум {max_len}).")
        return value
    if t == "number":
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError("Нужно число.")
        if num.is_integer() and not field.get("float"):
            num = int(num)
        if "min" in field and num < field["min"]:
            raise ValueError(f"Минимум {field['min']}.")
        if "max" in field and num > field["max"]:
            raise ValueError(f"Максимум {field['max']}.")
        return num
    if t == "select":
        allowed = [str(o[0]) if isinstance(o, (list, tuple)) else str(o) for o in field.get("options", [])]
        if str(value) not in allowed:
            raise ValueError("Недопустимое значение.")
        return str(value)
    raise ValueError("Неизвестный тип поля.")


def public_schema(schema: list[dict]) -> list[dict]:
    """Схема без python-объектов — для отправки в приложение."""
    result = []
    for field in schema:
        if field.get("type") not in FIELD_TYPES and field.get("type") != "section":
            continue
        item = {k: v for k, v in field.items() if not callable(v)}
        if "options" in item:
            item["options"] = [list(o) if isinstance(o, (list, tuple)) else [o, o] for o in item["options"]]
        result.append(item)
    return result


def get_route(spec: dict, name: str) -> Callable | None:
    routes = spec.get("routes") or {}
    func = routes.get(name)
    return func if callable(func) else None
