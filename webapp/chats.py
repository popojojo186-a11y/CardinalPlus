"""
Чаты с покупателями для приложения.

Откуда берутся данные:
- список чатов — из памяти Cardinal (account.get_chats()), его и так постоянно обновляет Runner;
- история чата — один запрос к FunPay при первом открытии, дальше новые сообщения приходят
  событиями Cardinal (BIND_TO_NEW_MESSAGE) и складываются в кэш без лишних запросов;
- если событие почему-то не пришло, а в списке чатов видно новое сообщение, история перечитывается
  (не чаще раза в HISTORY_RECHECK секунд на чат).

Отправка идёт через cardinal.send_message() — так же, как ответ из Telegram-бота.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

READ_PATH = os.path.join("storage", "cache", "webapp_chat_read.json")
HISTORY_RECHECK = 8      # сек: перечитать историю, если в списке чатов есть сообщение новее кэша
HISTORY_MAX_AGE = 300    # сек: на всякий случай перечитывать историю открытого чата раз в 5 минут
LIST_REFRESH = 30        # сек: если Cardinal ещё не загрузил список чатов, запросить его не чаще раза в 30 сек
MAX_TEXT = 2000
MAX_TEMPLATES = 50
MAX_IMAGE = 5 * 1024 * 1024


def _is_image(data: bytes) -> bool:
    """JPG, PNG, GIF или WEBP — по первым байтам файла, а не по названию."""
    return (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:6] in (b"GIF87a", b"GIF89a")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))

_MSG_DATE = re.compile(r'class="chat-msg-date"[^>]*?title="([^"]*)"[^>]*>\s*([^<]*?)\s*<')
_LIST_TIME = re.compile(r'class="contact-item-time"[^>]*>\s*([^<]*?)\s*<')
_AVATAR = re.compile(r'background-image:\s*url\(\s*[\'"]?([^\'")]+)')


class ChatError(Exception):
    pass


class ChatsService:
    def __init__(self, cardinal: Cardinal):
        self.c = cardinal
        self._lock = threading.RLock()
        self._hist: dict[int, dict] = {}          # id чата -> {"messages", "fetched", "last_id", "name", "interlocutor_id"}
        self._fetch_locks: dict[int, threading.Lock] = {}
        self._last_list_refresh = 0.0
        self._read: dict[str, int] = self._load_read()
        self._installed = False
        self.on_fetch = None   # (chat_id, name, messages) — загруженная переписка уходит в архив для поиска

    # ---------- подключение к событиям Cardinal ----------
    def install(self) -> None:
        if self._installed or not hasattr(self.c, "new_message_handlers"):
            return

        def on_new_message(cardinal, event):
            self.on_message(event.message)

        on_new_message.plugin_uuid = None  # встроенный обработчик, работает всегда
        self.c.new_message_handlers.append(on_new_message)
        self._installed = True

    # ---------- прочитанное ----------
    @staticmethod
    def _load_read() -> dict:
        try:
            with open(READ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_read(self) -> None:
        try:
            os.makedirs(os.path.dirname(READ_PATH), exist_ok=True)
            tmp = READ_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._read, f)
            os.replace(tmp, READ_PATH)
        except OSError:
            logger.debug("TRACEBACK", exc_info=True)

    def _mark_read(self, chat_id: int, msg_id: int) -> None:
        key = str(chat_id)
        with self._lock:
            if msg_id > self._read.get(key, 0):
                self._read[key] = msg_id
                self._save_read()

    # ---------- преобразование в JSON ----------
    def _my_id(self):
        return getattr(self.c.account, "id", None)

    def _msg(self, m) -> dict:
        found = _MSG_DATE.search(m.html or "")
        author_id = getattr(m, "author_id", None)
        return {
            "id": int(m.id or 0),
            "text": m.text,
            "image": getattr(m, "image_link", None),
            "author": getattr(m, "author", None),
            "mine": author_id == self._my_id(),
            "bot": bool(getattr(m, "by_bot", False)),
            "system": author_id == 0,
            "badge": getattr(m, "badge", None),
            "time": found.group(2) if found else None,
            "time_full": found.group(1) if found else None,
        }

    def _chat(self, ch) -> dict:
        html = getattr(ch, "html", "") or ""
        t = _LIST_TIME.search(html)
        a = _AVATAR.search(html)
        avatar = a.group(1) if a else None
        if avatar and (not avatar.startswith("http") or "/img/layout/avatar" in avatar):
            avatar = None
        read = self._read.get(str(ch.id), 0)
        return {
            "id": ch.id,
            "name": ch.name,
            "last_text": ch.last_message_text or "",
            "last_id": int(ch.node_msg_id or 0),
            "last_by_bot": bool(ch.last_by_bot),
            "unread": bool(ch.unread) and int(ch.node_msg_id or 0) > read,
            "time": t.group(1) if t else None,
            "avatar": avatar,
            "blacklisted": ch.name in getattr(self.c, "blacklist", []),
        }

    # ---------- список чатов ----------
    def list(self) -> dict:
        acc = self.c.account
        chats = acc.get_chats()
        if not chats and time.time() - self._last_list_refresh > LIST_REFRESH:
            self._last_list_refresh = time.time()
            try:
                chats = acc.get_chats(update=True)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ChatError("Не удалось загрузить чаты с FunPay. Попробуйте ещё раз через минуту.")
        items = [self._chat(ch) for ch in list(chats.values()) if isinstance(ch.id, int) and ch.name]
        items.sort(key=lambda x: -x["last_id"])
        return {"chats": items, "unread": sum(1 for i in items if i["unread"])}

    def unread_count(self) -> int:
        try:
            return self.list()["unread"]
        except Exception:
            return 0

    # ---------- история ----------
    def _shortcut(self, chat_id: int):
        try:
            return self.c.account.get_chat_by_id(chat_id)
        except Exception:
            return None

    def _fetch(self, chat_id: int, name: str | None) -> dict:
        lock = self._fetch_locks.setdefault(chat_id, threading.Lock())
        with lock:
            try:
                messages = self.c.account.get_chat_history(chat_id, interlocutor_username=name)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ChatError("Не удалось загрузить переписку с FunPay. Попробуйте ещё раз.")
            items = [self._msg(m) for m in messages if m.id]
            interlocutor = next((m.interlocutor_id for m in messages if getattr(m, "interlocutor_id", None)), None)
            name = name or next((m.chat_name for m in messages if m.chat_name), None)
            if self.on_fetch is not None:
                try:
                    self.on_fetch(chat_id, name, messages)
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
            with self._lock:
                old = self._hist.get(chat_id) or {}
                h = {"messages": items, "fetched": time.time(), "last_id": max([m["id"] for m in items], default=0),
                     "name": name or old.get("name"), "interlocutor_id": interlocutor or old.get("interlocutor_id")}
                self._hist[chat_id] = h
            return h

    def history(self, chat_id: int, since: int = 0, mark_read: bool = False) -> dict:
        ch = self._shortcut(chat_id)
        with self._lock:
            h = self._hist.get(chat_id)
        now = time.time()
        newer_in_list = bool(ch and h and int(ch.node_msg_id or 0) > h["last_id"])
        if h is None or (newer_in_list and now - h["fetched"] > HISTORY_RECHECK) or now - h["fetched"] > HISTORY_MAX_AGE:
            h = self._fetch(chat_id, ch.name if ch else (h or {}).get("name"))
        if mark_read:
            self._mark_read(chat_id, max(h["last_id"], int(ch.node_msg_id or 0) if ch else 0))
        with self._lock:
            messages = [m for m in h["messages"] if m["id"] > since]
        name = (ch.name if ch else None) or h.get("name")
        return {
            "chat": {"id": chat_id, "name": name, "interlocutor_id": h.get("interlocutor_id"),
                     "blacklisted": bool(name and name in getattr(self.c, "blacklist", [])),
                     "link": f"https://funpay.com/chat/?node={chat_id}"},
            "messages": messages,
            "last_id": h["last_id"],
            "full": since == 0,
        }

    def on_message(self, m) -> None:
        """Новое сообщение из Cardinal — дописываем в кэш, если этот чат уже открывали."""
        try:
            chat_id = m.chat_id if isinstance(m.chat_id, int) else int(m.chat_id)
        except (TypeError, ValueError):
            return
        if not m.id:
            return
        with self._lock:
            h = self._hist.get(chat_id)
            if h is None or m.id <= h["last_id"]:
                return
            h["messages"].append(self._msg(m))
            h["last_id"] = m.id
            if len(h["messages"]) > 300:
                del h["messages"][:-300]

    def info(self, chat_id: int) -> dict:
        """Ник и ID собеседника — для карточки покупателя."""
        ch = self._shortcut(chat_id)
        with self._lock:
            h = self._hist.get(chat_id) or {}
        return {"name": (ch.name if ch else None) or h.get("name"), "interlocutor_id": h.get("interlocutor_id")}

    # ---------- отправка ----------
    def send(self, chat_id: int, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise ChatError("Пустое сообщение.")
        if len(text) > MAX_TEXT:
            raise ChatError(f"Слишком длинное сообщение (максимум {MAX_TEXT} символов).")
        ch = self._shortcut(chat_id)
        with self._lock:
            h = self._hist.get(chat_id)
        name = (ch.name if ch else None) or (h or {}).get("name")
        try:
            result = self.c.send_message(chat_id, text, name, watermark=False)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            result = None
        if not result:
            raise ChatError("FunPay не принял сообщение. Подождите немного и попробуйте снова — "
                            "FunPay ограничивает частую отправку.")
        sent = self._remember_sent(chat_id, result)
        logger.info(f"Mini App: отправлено сообщение в чат {name or chat_id}")
        return {"ok": True, "messages": sent}

    def send_image(self, chat_id: int, data: bytes) -> dict:
        """Картинка из приложения: выгружаем на FunPay и отправляем так же, как это делает Cardinal ($photo=ID)."""
        if not data:
            raise ChatError("Пустая картинка.")
        if len(data) > MAX_IMAGE:
            raise ChatError("Картинка слишком большая (максимум 5 МБ).")
        if not _is_image(data):
            raise ChatError("Это не картинка. Можно отправить JPG, PNG, GIF или WEBP.")
        ch = self._shortcut(chat_id)
        with self._lock:
            h = self._hist.get(chat_id)
        name = (ch.name if ch else None) or (h or {}).get("name")
        try:
            image_id = self.c.account.upload_image(data, "chat")
        except Exception as e:
            logger.debug("TRACEBACK", exc_info=True)
            msg = getattr(e, "error_message", None)
            raise ChatError(f"FunPay не принял картинку{': ' + msg if msg else ''}. Попробуйте другую или чуть позже.")
        try:
            result = self.c.send_message(chat_id, f"$photo={image_id}", name, watermark=False)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            result = None
        if not result:
            raise ChatError("FunPay не принял картинку. Подождите немного и попробуйте снова.")
        sent = self._remember_sent(chat_id, result)
        logger.info(f"Mini App: отправлена картинка в чат {name or chat_id}")
        return {"ok": True, "messages": sent}

    def _remember_sent(self, chat_id: int, result) -> list[dict]:
        """Кладёт отправленные сообщения в кэш переписки и отмечает чат прочитанным."""
        sent = []
        with self._lock:
            h = self._hist.get(chat_id)
            for m in result:
                if not getattr(m, "id", 0):
                    if h is not None:
                        h["fetched"] = 0  # id неизвестен — перечитаем историю при следующем запросе
                    continue
                item = self._msg(m)
                item["mine"] = True
                sent.append(item)
                if h is not None and m.id > h["last_id"]:
                    h["messages"].append(item)
                    h["last_id"] = m.id
        if sent:
            self._mark_read(chat_id, max(i["id"] for i in sent))
        return sent

    # ---------- шаблоны ответов (общие с Telegram-ботом Cardinal) ----------
    def templates(self) -> list[str]:
        tg = self.c.telegram
        return list(getattr(tg, "answer_templates", None) or []) if tg else []

    def change_templates(self, action: str, text: str | None = None, index: int | None = None) -> list[str]:
        tg = self.c.telegram
        if tg is None:
            raise ChatError("Telegram-бот выключен — шаблоны хранятся в нём.")
        from tg_bot import utils as tg_utils
        items = tg.answer_templates
        if action == "add":
            text = (text or "").strip()
            if not text:
                raise ChatError("Пустой шаблон.")
            if len(text) > MAX_TEXT:
                raise ChatError(f"Слишком длинный шаблон (максимум {MAX_TEXT} символов).")
            if len(items) >= MAX_TEMPLATES:
                raise ChatError(f"Шаблонов не может быть больше {MAX_TEMPLATES}.")
            if text in items:
                raise ChatError("Такой шаблон уже есть.")
            items.append(text)
        elif action == "delete":
            if index is None or not 0 <= index < len(items):
                raise ChatError("Шаблон не найден.")
            items.pop(index)
        else:
            raise ChatError("Неизвестное действие.")
        tg_utils.save_answer_templates(items)
        return list(items)
