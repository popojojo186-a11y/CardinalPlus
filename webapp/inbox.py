"""
Входящие: «покупатель ждёт ответа» и поиск по всем чатам.

Ждёт ответа: покупатель написал, а вы ещё не ответили. Ответом считается сообщение, написанное
на сайте FunPay, из приложения или из Telegram-бота. Автоматика Cardinal (приветствие, автовыдача,
напоминания) ответом не считается — она отправляется с водяным знаком, а ручные ответы без него.
Если покупатель ждёт дольше N минут — один раз приходит напоминание в Telegram.

Поиск: все сообщения, которые видит Cardinal, складываются в локальный архив (SQLite). Старые переписки
можно догрузить кнопкой — по одному чату с паузой, чтобы не нагружать FunPay.
"""
from __future__ import annotations

import html
import logging
import os
import re
import sqlite3
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

DB_PATH = os.path.join("storage", "cache", "webapp_messages.db")
REMIND_LOOP = 30           # сек между проверками «ждёт ответа»
FORGET_AFTER = 24 * 3600   # дольше суток не напоминаем — наверное, разговор закончен
INDEX_PAUSE = 1.2          # сек между чатами при догрузке архива
INDEX_MAX = 150
_MSG_DATE = re.compile(r'class="chat-msg-date"[^>]*?title="([^"]*)"')
ORDER_RE = re.compile(r"#?([A-Z0-9]{8})")


class Inbox:
    def __init__(self, cardinal: Cardinal, automation):
        self.c = cardinal
        self.auto = automation
        self._lock = threading.RLock()
        self.waiting: dict[int, dict] = {}     # чат -> {"since", "name", "text", "reminded"}
        self._db_lock = threading.Lock()
        self._installed = False
        self._started = False
        self.index_job: dict | None = None
        self._init_db()

    # ---------- база ----------
    def _conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        return conn

    def _init_db(self) -> None:
        try:
            with self._db_lock, self._conn() as db:
                db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, chat_id INTEGER, chat_name TEXT,"
                           " author TEXT, mine INTEGER, text TEXT, low TEXT, ts INTEGER, when_text TEXT)")
                db.execute("CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id)")
        except sqlite3.Error:
            logger.warning("Mini App: не удалось открыть архив сообщений.")
            logger.debug("TRACEBACK", exc_info=True)

    def archive(self, messages, chat_id: int | None = None, chat_name: str | None = None, live: bool = False) -> int:
        """Кладёт сообщения в архив. live — сообщение пришло только что (известно точное время)."""
        rows = []
        my_id = getattr(self.c.account, "id", None)
        for m in messages:
            mid = int(getattr(m, "id", 0) or 0)
            text = getattr(m, "text", None) or ("[картинка]" if getattr(m, "image_link", None) else "")
            if not mid or not text:
                continue
            cid = chat_id if chat_id is not None else getattr(m, "chat_id", None)
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            name = chat_name or getattr(m, "chat_name", None) or ""
            author = getattr(m, "author", None) or ""
            found = _MSG_DATE.search(getattr(m, "html", "") or "")
            rows.append((mid, cid, name, author, int(getattr(m, "author_id", None) == my_id), text,
                         f"{name} {author} {text}".lower(), int(time.time()) if live else None,
                         found.group(1) if found else None))
        if not rows:
            return 0
        try:
            with self._db_lock, self._conn() as db:
                # время из «живого» сообщения не затираем, а имя чата и текст обновляем
                db.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                               "chat_name=CASE WHEN excluded.chat_name!='' THEN excluded.chat_name ELSE chat_name END,"
                               " text=excluded.text, low=excluded.low, ts=COALESCE(ts, excluded.ts),"
                               " when_text=COALESCE(excluded.when_text, when_text)", rows)
            return len(rows)
        except sqlite3.Error:
            logger.debug("TRACEBACK", exc_info=True)
            return 0

    def archive_stats(self) -> dict:
        try:
            with self._db_lock, self._conn() as db:
                n, chats = db.execute("SELECT COUNT(*), COUNT(DISTINCT chat_id) FROM messages").fetchone()
        except sqlite3.Error:
            n = chats = 0
        return {"messages": n, "archived_chats": chats, "job": self.index_job}

    def search(self, query: str, orders: list[dict] | None = None, limit: int = 60) -> dict:
        q = " ".join(str(query or "").split()).lower()
        if len(q) < 2:
            raise ValueError("Введите хотя бы 2 символа.")
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        try:
            with self._db_lock, self._conn() as db:
                rows = db.execute("SELECT id, chat_id, chat_name, author, mine, text, ts, when_text FROM messages "
                                  "WHERE low LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?", (like, limit)).fetchall()
        except sqlite3.Error:
            logger.debug("TRACEBACK", exc_info=True)
            rows = []
        results = [{"id": r[0], "chat_id": r[1], "chat_name": r[2], "author": r[3], "mine": bool(r[4]),
                    "text": r[5], "ts": r[6], "when": r[7]} for r in rows]
        # чаты по нику — даже если сообщений в архиве нет
        chats = []
        try:
            for ch in list(self.c.account.get_chats().values()):
                if isinstance(ch.id, int) and ch.name and q in ch.name.lower():
                    chats.append({"id": ch.id, "name": ch.name, "last_text": ch.last_message_text or ""})
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
        # номер заказа -> чат покупателя
        found_orders = []
        m = ORDER_RE.fullmatch(q.upper().lstrip("#")) if orders is not None else None
        if m:
            for o in orders:
                if str(o.get("id", "")).upper() == m.group(1):
                    chat = None
                    try:
                        ch = self.c.account.get_chat_by_name(o.get("buyer"))
                        chat = ch.id if ch else None
                    except Exception:
                        pass
                    found_orders.append({"id": o["id"], "buyer": o.get("buyer"), "description": o.get("description"),
                                         "chat_id": chat, "price": o.get("price"), "currency": o.get("currency")})
        return {"results": results, "chats": chats[:20], "orders": found_orders, **self.archive_stats()}

    # ---------- догрузка архива ----------
    def start_index(self, count: int) -> dict:
        count = max(1, min(INDEX_MAX, int(count or 30)))
        with self._lock:
            if self.index_job and self.index_job.get("running"):
                return self.index_job
            self.index_job = {"running": True, "done": 0, "total": 0, "messages": 0, "error": None, "started": int(time.time())}
            job = self.index_job
        threading.Thread(target=self._run_index, args=(job, count), daemon=True, name="webapp-index").start()
        return job

    def _run_index(self, job: dict, count: int) -> None:
        try:
            chats = [ch for ch in self.c.account.get_chats().values() if isinstance(ch.id, int) and ch.name]
            chats.sort(key=lambda ch: -int(ch.node_msg_id or 0))
            chats = chats[:count]
            job["total"] = len(chats)
            for ch in chats:
                try:
                    msgs = self.c.account.get_chat_history(ch.id, interlocutor_username=ch.name)
                    job["messages"] += self.archive(msgs, ch.id, ch.name)
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
                job["done"] += 1
                time.sleep(INDEX_PAUSE)
        except Exception as e:
            job["error"] = "Не удалось загрузить список чатов с FunPay."
            logger.debug("TRACEBACK", exc_info=True)
        finally:
            job["running"] = False
            job["ended"] = int(time.time())

    # ---------- события Cardinal ----------
    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        if hasattr(self.c, "new_message_handlers"):
            def on_new_message(cardinal, event):
                self.on_message(event.message)
            on_new_message.plugin_uuid = None
            self.c.new_message_handlers.append(on_new_message)
        # ручной ответ (приложение, Telegram) идёт через cardinal.send_message(..., watermark=False)
        original = getattr(self.c, "send_message", None)
        if original is not None:
            inbox = self

            def send_message(chat_id, message_text, chat_name=None, *args, **kwargs):
                result = original(chat_id, message_text, chat_name, *args, **kwargs)
                if result and kwargs.get("watermark") is False:
                    inbox.answered(chat_id)
                return result
            self.c.send_message = send_message

    def _commands(self) -> set[str]:
        cfg = getattr(self.c, "AR_CFG", None)
        out = set()
        try:
            for section in cfg.sections():
                out.update(x.strip().lower() for x in section.split("|") if x.strip())
        except Exception:
            pass
        return out

    def _greeting_bits(self) -> list[str]:
        """Неизменные куски текста приветствия — по ним узнаём автоприветствие Cardinal."""
        try:
            cfg = self.c.MAIN_CFG["Greetings"]
            text = cfg.get("greetingsText", "") if cfg.getboolean("sendGreetings") else ""
        except Exception:
            text = ""
        return [p.strip().lower() for p in re.split(r"\$\w+(?:=\S*)?", text) if len(p.strip()) >= 8]

    def on_message(self, m) -> None:
        try:
            chat_id = int(m.chat_id)
        except (TypeError, ValueError):
            return
        self.archive([m], chat_id, getattr(m, "chat_name", None), live=True)
        author_id = getattr(m, "author_id", None)
        if author_id == 0 or author_id is None:
            return  # системные сообщения FunPay
        text = (getattr(m, "text", None) or "").strip()
        if author_id == getattr(self.c.account, "id", None):
            low = text.lower()
            if any(bit in low for bit in self._greeting_bits()):
                return  # автоприветствие — это не ответ
            self.answered(chat_id)
            return
        if text and text.lower() in self._commands():
            return  # команду обработает автоответчик
        with self._lock:
            if chat_id not in self.waiting:
                self.waiting[chat_id] = {"since": time.time(), "name": getattr(m, "chat_name", None) or getattr(m, "author", None),
                                         "text": text or "[картинка]", "reminded": False}
            else:
                self.waiting[chat_id]["text"] = text or "[картинка]"

    def answered(self, chat_id) -> None:
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.waiting.pop(chat_id, None)

    def waiting_info(self) -> dict[int, int]:
        """Чат -> сколько секунд ждёт (только если включено напоминание)."""
        if not self.auto.flag("waitReply"):
            return {}
        now = time.time()
        with self._lock:
            return {cid: int(now - w["since"]) for cid, w in self.waiting.items() if now - w["since"] < FORGET_AFTER}

    def minutes(self) -> int:
        try:
            return max(1, min(720, int(self.auto.get("waitReplyMinutes"))))
        except (TypeError, ValueError):
            return 10

    def check_waiting(self, now: float | None = None) -> int:
        if not self.auto.flag("waitReply"):
            return 0
        now = now or time.time()
        limit = self.minutes() * 60
        due = []
        with self._lock:
            for cid, w in list(self.waiting.items()):
                if now - w["since"] > FORGET_AFTER:
                    self.waiting.pop(cid, None)
                elif not w["reminded"] and now - w["since"] >= limit:
                    w["reminded"] = True
                    due.append((cid, dict(w)))
        for cid, w in due:
            self._remind(cid, w, int((now - w["since"]) // 60))
        return len(due)

    def _remind(self, chat_id: int, w: dict, mins: int) -> None:
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            return
        name = w.get("name") or f"чат {chat_id}"
        text = (f"⏰ <b>{html.escape(name)} ждёт ответа уже {mins} мин</b>\n"
                f"«{html.escape(w['text'][:300])}»")
        kb = None
        try:
            from tg_bot import keyboards
            kb = keyboards.reply(chat_id, name, extend=True)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
        for user_id in list(getattr(tg, "authorized_users", {}) or {}):
            try:
                tg.bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        def loop():
            while True:
                try:
                    self.check_waiting()
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
                time.sleep(REMIND_LOOP)
        threading.Thread(target=loop, daemon=True, name="webapp-inbox").start()
