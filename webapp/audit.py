"""
Журнал действий: что и когда меняли в приложении (и что сделала автоматика Cardinal+).

Тексты сообщений, пароли и ключи в журнал не попадают — только что сделано и с чем.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

logger = logging.getLogger("FPC.webapp")

PATH = os.path.join("storage", "cache", "webapp_audit.jsonl")
MAX_BYTES = 3 * 1024 * 1024
KINDS = {"chats": "Чаты", "lots": "Лоты", "settings": "Настройки", "plugins": "Плагины", "stock": "Склад",
         "reviews": "Отзывы", "money": "Деньги", "system": "Система", "other": "Другое"}


def _short(v, n: int = 60) -> str:
    v = " ".join(str(v or "").split())
    return v if len(v) <= n else v[:n - 1] + "…"


class Audit:
    def __init__(self, cardinal=None):
        self.c = cardinal
        self._lock = threading.Lock()
        self.labels: dict[tuple[str, str], str] = {}   # (секция, опция) -> понятное название (заполняет сервер)
        self.notification_names: dict[str, str] = {}   # код типа уведомлений -> название

    # ---------- запись ----------
    def add(self, user: dict | None, kind: str, text: str) -> None:
        rec = {"t": int(time.time()), "kind": kind if kind in KINDS else "other", "text": _short(text, 200)}
        if user:
            rec["user"] = user.get("id")
            rec["name"] = user.get("username") or user.get("first_name") or ""
            rec["via"] = user.get("via") or ""
        try:
            with self._lock:
                os.makedirs(os.path.dirname(PATH), exist_ok=True)
                with open(PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if os.path.getsize(PATH) > MAX_BYTES:
                    with open(PATH, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    with open(PATH + ".tmp", "w", encoding="utf-8") as f:
                        f.writelines(lines[len(lines) // 2:])
                    os.replace(PATH + ".tmp", PATH)
        except OSError:
            logger.debug("TRACEBACK", exc_info=True)

    def read(self, kind: str = "", q: str = "", limit: int = 300) -> dict:
        items = []
        try:
            with self._lock, open(PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            lines = []
        q = (q or "").strip().lower()
        counts: dict[str, int] = {}
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            counts[rec.get("kind", "other")] = counts.get(rec.get("kind", "other"), 0) + 1
            if kind and rec.get("kind") != kind:
                continue
            if q and q not in f"{rec.get('text', '')} {rec.get('name', '')}".lower():
                continue
            if len(items) < limit:
                items.append(rec)
        return {"items": items, "counts": counts, "kinds": KINDS}

    # ---------- описание запроса приложения ----------
    def describe(self, path: str, body: dict, result) -> tuple[str, str] | None:
        """(раздел, текст) для успешного POST-запроса приложения или None — не записывать."""
        b = body or {}
        r = result if isinstance(result, dict) else {}
        m = re.fullmatch(r"/api/chats/(\d+)/(send|image)", path)
        if m:
            name = self._chat_name(int(m.group(1)))
            return "chats", f"{'Картинка' if m.group(2) == 'image' else 'Ответ'} в чат {name}"
        if path == "/api/chats/templates":
            return "chats", f"Шаблоны ответов: {'добавлен' if b.get('action') == 'add' else 'удалён'} шаблон"
        if path == "/api/chats/index":
            return "chats", "Загрузка старых переписок в архив для поиска"
        m = re.fullmatch(r"/api/lots/(\d+)", path)
        if m:
            parts = []
            if b.get("price") is not None:
                parts.append(f"цена {r.get('old_price')} → {r.get('price')}")
            if b.get("active") is not None:
                parts.append("включён" if r.get("active") else "выключен")
            return "lots", f"Лот №{m.group(1)}: {', '.join(parts) or 'изменён'}"
        m = re.fullmatch(r"/api/lots/(\d+)/copy", path)
        if m:
            return "lots", f"Копия лота №{m.group(1)} ({'включена' if b.get('active') else 'выключена'})"
        if path == "/api/lots/bulk":
            return "lots", f"Массовое изменение лотов: {len(b.get('ids') or [])} шт."
        if path == "/api/lots/demo":
            return "lots", f"Демо-режим лотов {'включён' if b.get('enabled') else 'выключен'}"
        if path == "/api/lots/subcategory":
            return "lots", f"Добавлена подкатегория {b.get('id')}"
        if path == "/api/lots/schedule":
            act = {"save": "сохранено", "delete": "удалено", "toggle": "включено" if b.get("enabled") else "выключено"}
            return "lots", f"Расписание лотов {act.get(b.get('action'), 'изменено')}" + \
                (f": «{_short((b.get('rule') or {}).get('name'), 40)}»" if b.get("action") == "save" else "")
        m = re.fullmatch(r"/api/blacklist/(add|remove)", path)
        if m:
            return "settings", f"Чёрный список: {'добавлен' if m.group(1) == 'add' else 'убран'} {_short(b.get('nickname'), 40)}"
        label = self.labels.get((str(b.get("section")), str(b.get("option")))) or f"{b.get('section')}.{b.get('option')}"
        if path == "/api/settings":
            return "settings", f"«{label}» — {'включено' if r.get('value') else 'выключено'}"
        if path == "/api/settings/text":
            return "settings", f"Изменено: «{label}»"
        if path == "/api/notifications":
            name = self.notification_names.get(str(b.get("type")), f"тип {b.get('type')}")
            return "settings", f"Уведомления в Telegram: «{name}» — {'включены' if r.get('value') else 'выключены'}"
        if path == "/api/automation/action":
            return "settings", "Отчёт за день отправлен вручную"
        if path.startswith("/api/stock/"):
            what = b.get("name") or b.get("title") or ""
            return "stock", f"Склад: {b.get('action')} {_short(what, 50)}".strip()
        if path == "/api/reviews/reply":
            return "reviews", f"{'Удалён ответ' if b.get('delete') else 'Ответ'} на отзыв к заказу #{b.get('order_id')}"
        if path == "/api/reviews/fetch":
            return "reviews", "Загрузка отзывов по последним заказам"
        if path == "/api/costs":
            if "default_pct" in b:
                return "money", f"Себестоимость по умолчанию: {b.get('default_pct')}% от цены"
            return "money", f"Себестоимость «{_short(b.get('title'), 50)}»: {b.get('cost') if str(b.get('cost') or '').strip() else 'убрана'}"
        if path == "/api/plan":
            return "money", f"План продаж на месяц: {b.get('amount')}"
        if path == "/api/backup/make":
            return "system", "Создана резервная копия" + (" (отправлена в Telegram)" if b.get("send") else "")
        if path == "/api/backup/inspect":
            return None  # только проверка пароля
        if path == "/api/backup/restore":
            return "system", f"Восстановление из резервной копии: файлов {r.get('files')}"
        if path == "/api/restart":
            return "system", "Перезапуск Cardinal"
        if path == "/api/balance/refresh":
            return None
        if path == "/api/login-link":
            return "system", "Вход в Панель через браузер (одноразовая ссылка)"
        m = re.fullmatch(r"/api/plugins/([0-9a-fA-F-]{36})/(settings|toggle|delete|rollback|call/[\w\-]+)", path)
        if m:
            name = self._plugin_name(m.group(1)) or r.get("name") or "плагин"
            act = m.group(2)
            if act == "settings":
                return "plugins", f"{name}: настройка {b.get('key')}"
            if act == "toggle":
                return "plugins", f"{name}: {'включён' if r.get('enabled') else 'выключен'}"
            if act == "delete":
                return "plugins", f"{name}: удалён"
            if act == "rollback":
                return "plugins", f"{name}: возвращена прошлая версия"
            route = act.split("/", 1)[1]
            if route in ("accounts", "lots", "stats"):
                return None  # только чтение
            return "plugins", f"{name}: действие «{route}»"
        if path == "/api/plugins/install":
            return "plugins", f"{'Обновлён' if r.get('update') else 'Установлен'} плагин {r.get('name')}"
        if path == "/api/plugins/inspect":
            return None
        return "other", f"POST {path}"

    def _chat_name(self, chat_id: int) -> str:
        try:
            ch = self.c.account.get_chat_by_id(chat_id)
            if ch and ch.name:
                return ch.name
        except Exception:
            pass
        return f"№{chat_id}"

    def _plugin_name(self, uuid: str) -> str | None:
        try:
            p = self.c.plugins.get(uuid)
            return p.name if p else None
        except Exception:
            return None
