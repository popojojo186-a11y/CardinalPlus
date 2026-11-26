"""
Сторож и уведомления Cardinal+.

- Сторож следит, получает ли Cardinal обновления с FunPay. Если связи нет дольше N минут
  (устарел golden_key, FunPay недоступен, пропал интернет) — сообщает в Telegram, а когда связь
  вернулась — пишет, что всё снова работает. Ядро Cardinal не меняется: оборачивается только
  метод Runner.get_updates у запущенного экземпляра.
- Тихие часы: ночью уведомления приходят без звука или копятся и приходят утром одним сообщением.
- Выбор уведомлений: какие типы уведомлений Cardinal присылать (те же настройки, что в боте).
"""
from __future__ import annotations

import datetime
import html
import logging
import re
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

CHECK_EVERY = 20        # сек между проверками сторожа
HOLD_MAX = 200          # сколько уведомлений копить в тихие часы
TAG_RE = re.compile(r"<[^>]+>")

# Типы уведомлений Cardinal (tg_bot.utils.NotificationTypes): код, название, пояснение
NOTIFICATION_TYPES = [
    ("4", "Новые заказы", "Покупатель оплатил заказ"),
    ("2", "Сообщения", "Покупатель написал в чат"),
    ("5", "Подтверждения", "Покупатель подтвердил заказ"),
    ("5r", "Отзывы", "Новый или изменённый отзыв"),
    ("8", "Выдача товара", "Автовыдача отправила товар"),
    ("3", "Команды", "Покупатель написал команду автоответчика"),
    ("6", "Восстановление лотов", "Лот снова включён после продажи"),
    ("7", "Выключение лотов", "Лот выключен: закончился товар"),
    ("9", "Поднятие лотов", "Автоподнятие подняло лоты"),
    ("1", "Запуск бота", "Cardinal запустился"),
    ("10", "Плагины", "Уведомления от плагинов"),
    ("11", "Новости Cardinal", "Объявления разработчиков"),
    ("12", "Реклама", "Рекламные объявления"),
]
NEVER_HOLD = {"13", "14"}  # критичные уведомления Cardinal не откладываем


def _clock(value: str, default: tuple[int, int]) -> tuple[int, int]:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(value or ""))
    return (int(m.group(1)), int(m.group(2))) if m else default


def in_window(now: datetime.datetime, start: str, end: str) -> bool:
    """Попадает ли время в окно «с start до end»; окно может переходить через полночь (23:00–08:00)."""
    s, e = _clock(start, (23, 0)), _clock(end, (8, 0))
    t = (now.hour, now.minute)
    if s == e:
        return False
    return s <= t < e if s < e else (t >= s or t < e)


def explain_error(exc: BaseException | None) -> str:
    """Понятная причина, почему Cardinal не получает обновления."""
    if exc is None:
        return "Cardinal перестал запрашивать обновления (возможно, завис или был остановлен)."
    name = exc.__class__.__name__
    text = str(exc)[:200]
    if name == "UnauthorizedError" or "401" in text or "Unauthorized" in text:
        return "FunPay не пускает аккаунт — скорее всего, устарел golden_key. Обновите его в configs/_main.cfg и перезапустите Cardinal."
    if name in ("ConnectionError", "ConnectTimeout", "ReadTimeout", "Timeout", "TimeoutError") or "Max retries" in text:
        return "Нет связи с FunPay: пропал интернет или FunPay недоступен."
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return "FunPay временно ограничил запросы (слишком часто). Обычно проходит само через несколько минут."
    if status and status >= 500:
        return f"FunPay отвечает ошибкой {status} — похоже, проблемы на стороне FunPay."
    if status == 403:
        return "FunPay отвечает «доступ запрещён» (403): возможно, нужна проверка аккаунта или сменился IP."
    return f"Ошибка при получении обновлений: {name}."


class Guard:
    def __init__(self, cardinal: Cardinal, automation, audit=None):
        self.c = cardinal
        self.auto = automation
        self.audit = audit
        self._lock = threading.RLock()
        self.last_ok: float | None = None
        self.last_error: BaseException | None = None
        self.last_error_at: float | None = None
        self.down_since: float | None = None
        self.alerted = False
        self.wrapped_runner = None
        self.held: list[dict] = []
        self._quiet_was = False
        self._started = False
        self._installed_tg = False

    # ---------- подключение ----------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.install_telegram()
        threading.Thread(target=self._loop, daemon=True, name="webapp-guard").start()

    def wrap_runner(self) -> bool:
        runner = getattr(self.c, "runner", None)
        if runner is None or runner is self.wrapped_runner:
            return runner is not None
        original = runner.get_updates

        def get_updates(*args, **kwargs):
            try:
                result = original(*args, **kwargs)
            except BaseException as e:
                with self._lock:
                    self.last_error, self.last_error_at = e, time.time()
                raise
            with self._lock:
                self.last_ok = time.time()
            return result

        runner.get_updates = get_updates
        self.wrapped_runner = runner
        with self._lock:
            self.last_ok = self.last_ok or time.time()
        return True

    def install_telegram(self) -> None:
        tg = getattr(self.c, "telegram", None)
        if tg is None or self._installed_tg:
            return
        self._installed_tg = True
        bot = tg.bot
        guard = self

        # тихие часы: всё, что бот отправляет, приходит без звука
        for name in ("send_message", "send_photo", "send_document"):
            original = getattr(bot, name, None)
            if original is None:
                continue

            def make(orig):
                def silent(*args, **kwargs):
                    if guard.quiet_now() and "disable_notification" not in kwargs:
                        kwargs["disable_notification"] = True
                    return orig(*args, **kwargs)
                return silent
            setattr(bot, name, make(original))

        # режим «копить до утра»: уведомления Cardinal не отправляются, а запоминаются
        send_notification = getattr(tg, "send_notification", None)
        if send_notification is not None:
            def held_notification(text, keyboard=None, notification_type="10", photo=None, pin=False, **kwargs):
                if guard.quiet_now() and guard.auto.get("quietMode") == "hold" and str(notification_type) not in NEVER_HOLD:
                    guard.hold(text, notification_type)
                    return None
                return send_notification(text, keyboard, notification_type, photo, pin, **kwargs)
            tg.send_notification = held_notification

    # ---------- тихие часы ----------
    def quiet_now(self, now: datetime.datetime | None = None) -> bool:
        if not self.auto.flag("quietHours"):
            return False
        return in_window(now or datetime.datetime.now(), self.auto.get("quietFrom"), self.auto.get("quietTo"))

    def hold(self, text, notification_type) -> None:
        plain = TAG_RE.sub("", str(text or "")).strip()
        first = next((line.strip() for line in plain.splitlines() if line.strip()), "Уведомление")
        with self._lock:
            if len(self.held) < HOLD_MAX:
                self.held.append({"t": time.time(), "type": str(notification_type), "text": first[:120]})

    def flush_held(self) -> int:
        with self._lock:
            items, self.held = self.held, []
        if not items:
            return 0
        names = {code: name for code, name, _ in NOTIFICATION_TYPES}
        counts: dict[str, int] = {}
        for it in items:
            counts[it["type"]] = counts.get(it["type"], 0) + 1
        head = ", ".join(f"{names.get(k, 'прочее').lower()} — {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        lines = [f"🌙 <b>Пока были тихие часы, пришло уведомлений: {len(items)}</b>", head, ""]
        for it in items[-15:]:
            lines.append(f"{datetime.datetime.fromtimestamp(it['t']).strftime('%H:%M')} · {html.escape(it['text'])}")
        if len(items) > 15:
            lines.append(f"…и ещё {len(items) - 15} раньше")
        self.send_all("\n".join(lines))
        return len(items)

    # ---------- сторож ----------
    def minutes(self) -> int:
        try:
            return max(2, min(120, int(self.auto.get("watchdogMinutes"))))
        except (TypeError, ValueError):
            return 5

    def status(self) -> dict:
        with self._lock:
            last_ok, err, down = self.last_ok, self.last_error, self.down_since
            err_at = self.last_error_at
        enabled = self.auto.flag("watchdog")
        if self.wrapped_runner is None or last_ok is None:
            state = "unknown"
        elif down is not None:
            state = "down"
        else:
            state = "ok"
        fresh_error = err is not None and err_at is not None and (last_ok is None or err_at > last_ok)
        return {"enabled": enabled, "state": state, "last_ok": int(last_ok) if last_ok else None,
                "down_since": int(down) if down else None,
                "reason": explain_error(err if fresh_error else None) if state == "down" else None,
                "minutes": self.minutes(), "quiet": self.quiet_now(), "held": len(self.held)}

    def check(self, now: float | None = None) -> str:
        """Одна проверка. Возвращает «ok», «down» или «unknown»."""
        now = now or time.time()
        if not self.wrap_runner():
            return "unknown"
        with self._lock:
            last_ok = self.last_ok or now
            err = self.last_error if self.last_error_at and self.last_error_at > last_ok else None
        limit = self.minutes() * 60
        if now - last_ok > limit:
            with self._lock:
                if self.down_since is None:
                    self.down_since = last_ok
            if self.auto.flag("watchdog") and not self.alerted:
                self.alerted = True
                mins = int((now - last_ok) // 60)
                self.send_all(f"🚨 <b>Cardinal не получает обновления с FunPay уже {mins} мин</b>\n\n"
                              f"{html.escape(explain_error(err))}\n\n"
                              f"Пока связи нет, заказы, сообщения и автовыдача не обрабатываются. "
                              f"Когда всё заработает, я напишу.")
                self._audit(f"Сторож: нет связи с FunPay {mins} мин")
            return "down"
        with self._lock:
            was_down, since = self.down_since, self.down_since
            self.down_since = None
        if was_down is not None and self.alerted:
            mins = max(1, int((now - since) // 60))
            self.send_all(f"✅ <b>Связь с FunPay восстановилась</b>\nCardinal снова получает заказы и сообщения "
                          f"(не было связи ~{mins} мин).")
            self._audit("Сторож: связь с FunPay восстановилась")
        self.alerted = False
        return "ok"

    def _audit(self, text: str) -> None:
        if self.audit is not None:
            try:
                self.audit.add(None, "system", text)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)

    def send_all(self, text: str) -> int:
        """Сообщение всем, кто вошёл в Telegram-бота Cardinal (мимо настроек уведомлений — это важно)."""
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            return 0
        sent = 0
        for user_id in list(getattr(tg, "authorized_users", {}) or {}):
            try:
                tg.bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
        return sent

    def _loop(self) -> None:
        while True:
            try:
                self.check()
                quiet = self.quiet_now()
                if self._quiet_was and not quiet:
                    self.flush_held()
                self._quiet_was = quiet
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(CHECK_EVERY)

    # ---------- выбор уведомлений ----------
    def notification_chats(self, user_id: int) -> dict:
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            return {"chats": [], "types": []}
        settings = getattr(tg, "notification_settings", {}) or {}
        ids = list(dict.fromkeys([str(user_id), *map(str, settings.keys())]))
        chats = []
        for cid in ids:
            title = "Этот чат с ботом" if cid == str(user_id) else (f"Группа {cid}" if cid.startswith("-") else f"Чат {cid}")
            chats.append({"id": cid, "title": title, "known": cid in settings,
                          "values": {code: bool(tg.is_notification_enabled(cid, code)) for code, *_ in NOTIFICATION_TYPES}})
        return {"chats": chats, "types": [{"code": c, "label": l, "hint": h} for c, l, h in NOTIFICATION_TYPES]}

    def set_notification(self, chat_id: str, code: str, value: bool) -> bool:
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            raise ValueError("Telegram-бот выключен.")
        if code not in {c for c, *_ in NOTIFICATION_TYPES}:
            raise ValueError("Неизвестный тип уведомлений.")
        chat_id = str(chat_id)
        if not re.fullmatch(r"-?\d{1,20}", chat_id):
            raise ValueError("Неизвестный чат.")
        if bool(tg.is_notification_enabled(chat_id, code)) != bool(value):
            tg.toggle_notification(chat_id, code)
        return bool(tg.is_notification_enabled(chat_id, code))
