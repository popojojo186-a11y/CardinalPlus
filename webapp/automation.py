"""
Автоматизация Cardinal+ (работает в фоне, пока запущен Cardinal):
- напоминание подтвердить заказ — покупателю, который давно оплатил, но не подтвердил выполнение;
- отчёт за день — каждый вечер в Telegram: заказы, выручка, баланс, склад.

Настройки хранятся в storage/cache/webapp_automation.json (не в конфиге Cardinal),
поэтому обычный Cardinal без приложения про них не знает и ничего не ломается.
"""
from __future__ import annotations

import datetime
import html
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

PATH = os.path.join("storage", "cache", "webapp_automation.json")
DEFAULTS = {
    "confirmReminder": False,
    "confirmReminderText": "Здравствуйте, $username! Если с заказом #$order_id всё в порядке, подтвердите его, пожалуйста, "
                           "на странице заказа: $order_link\nСпасибо за покупку! 🙂",
    "confirmReminderHours": "6",
    "confirmReminderRepeat": "24",
    "dailyReport": False,
    "dailyReportTime": "23:00",
    # контроль и уведомления (webapp/guard.py, inbox.py, reviews.py)
    "waitReply": True,
    "waitReplyMinutes": "10",
    "badReviewAlert": True,
    "watchdog": True,
    "watchdogMinutes": "5",
    "quietHours": False,
    "quietFrom": "23:00",
    "quietTo": "08:00",
    "quietMode": "silent",
}
NUMBERS = {"waitReplyMinutes": (1, 720, "минут"), "watchdogMinutes": (2, 120, "минут")}
REMIND_CHECK = 600     # сек: как часто проверять неподтверждённые заказы
REMIND_MAX_AGE = 72    # ч: старше этого не напоминаем (скорее всего, спор или ручная выдача)
REMIND_PER_CHECK = 5   # не больше 5 напоминаний за одну проверку
REMIND_PAUSE = 15      # сек между напоминаниями разным покупателям (FunPay не любит частые сообщения)
TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


class AutomationService:
    def __init__(self, cardinal: Cardinal, sales, stock=None):
        self.c = cardinal
        self.sales = sales
        self.stock = stock
        self._lock = threading.RLock()
        data = self._load()
        self.settings = {**DEFAULTS, **{k: v for k, v in data.get("settings", {}).items() if k in DEFAULTS}}
        self.state = {"reminded": dict(data.get("reminded") or {}), "report_sent": data.get("report_sent")}
        self._started = False
        self._last_remind_check = 0.0

    # ---------- хранение ----------
    @staticmethod
    def _load() -> dict:
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        with self._lock:
            # старые отметки о напоминаниях больше не нужны
            cutoff = time.time() - 14 * 86400
            self.state["reminded"] = {k: v for k, v in self.state["reminded"].items() if v.get("last", 0) > cutoff}
            data = {"settings": self.settings, **self.state}
            try:
                os.makedirs(os.path.dirname(PATH), exist_ok=True)
                tmp = PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, PATH)
            except OSError:
                logger.debug("TRACEBACK", exc_info=True)

    def get(self, key: str):
        return self.settings.get(key, DEFAULTS.get(key))

    def flag(self, key: str) -> bool:
        return bool(self.get(key))

    def set_flag(self, key: str, value: bool) -> bool:
        with self._lock:
            self.settings[key] = bool(value)
            if key == "dailyReport" and value:
                # включили после времени отчёта — сегодняшний не шлём, первый придёт завтра (или кнопкой «сейчас»)
                if self._report_due(datetime.datetime.now()):
                    self.state["report_sent"] = datetime.date.today().isoformat()
            self._save()
        return self.settings[key]

    def set_text(self, key: str, value: str) -> str:
        value = str(value or "").replace("\r\n", "\n").strip()
        if key in ("confirmReminderHours", "confirmReminderRepeat"):
            try:
                num = int(float(value.replace(",", ".")))
            except ValueError:
                raise ValueError("Нужно целое число часов.")
            low = 1 if key == "confirmReminderHours" else 0
            if not low <= num <= 72:
                raise ValueError(f"Число от {low} до 72.")
            value = str(num)
        elif key in NUMBERS:
            low, high, unit = NUMBERS[key]
            try:
                num = int(float(value.replace(",", ".")))
            except ValueError:
                raise ValueError(f"Нужно целое число {unit}.")
            if not low <= num <= high:
                raise ValueError(f"Число от {low} до {high}.")
            value = str(num)
        elif key == "quietMode":
            if value not in ("silent", "hold"):
                raise ValueError("Недопустимое значение.")
        elif key in ("dailyReportTime", "quietFrom", "quietTo"):
            m = TIME_RE.fullmatch(value)
            if not m:
                raise ValueError("Время в формате ЧЧ:ММ, например 23:00.")
            value = f"{int(m.group(1)):02d}:{m.group(2)}"
        elif key == "confirmReminderText":
            if not value:
                raise ValueError("Текст напоминания не может быть пустым.")
            if len(value) > 1000:
                raise ValueError("Слишком длинный текст (максимум 1000 символов).")
        else:
            raise ValueError("Неизвестная настройка.")
        with self._lock:
            self.settings[key] = value
            if key == "dailyReportTime" and self._report_due(datetime.datetime.now()):
                self.state["report_sent"] = datetime.date.today().isoformat()
            self._save()
        return value

    # ---------- фоновый цикл ----------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True, name="webapp-automation").start()

    def _loop(self) -> None:
        time.sleep(60)  # даём Cardinal спокойно запуститься
        while True:
            try:
                now = datetime.datetime.now()
                if self.flag("dailyReport") and self._report_due(now) and self.state.get("report_sent") != now.date().isoformat():
                    self.send_report()
                if self.flag("confirmReminder") and time.time() - self._last_remind_check > REMIND_CHECK:
                    self._last_remind_check = time.time()
                    self.check_reminders()
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(30)

    def _report_due(self, now: datetime.datetime) -> bool:
        m = TIME_RE.fullmatch(str(self.get("dailyReportTime")))
        h, mi = (int(m.group(1)), int(m.group(2))) if m else (23, 0)
        return (now.hour, now.minute) >= (h, mi)

    # ---------- напоминание подтвердить заказ ----------
    def check_reminders(self) -> int:
        try:
            hours = max(1, int(self.get("confirmReminderHours")))
            repeat = max(0, int(self.get("confirmReminderRepeat")))
        except (TypeError, ValueError):
            hours, repeat = 6, 24
        try:
            _, orders, *_ = self.c.account.get_sales(include_closed=False, include_refunded=False)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            return 0
        now = datetime.datetime.now()
        blacklist = set(getattr(self.c, "blacklist", []) or [])
        sent = 0
        for order in orders:
            if sent >= REMIND_PER_CHECK:
                break
            status = getattr(getattr(order, "status", None), "name", "").lower()
            if status != "paid" or not order.date or order.buyer_username in blacklist:
                continue
            age = (now - order.date).total_seconds() / 3600
            if age < hours or age > REMIND_MAX_AGE:
                continue
            rec = self.state["reminded"].get(order.id) or {"count": 0, "last": 0}
            if rec["count"] >= 2 or (rec["count"] == 1 and (not repeat or time.time() - rec["last"] < repeat * 3600)):
                continue
            if self._remind(order):
                rec = {"count": rec["count"] + 1, "last": time.time()}
                with self._lock:
                    self.state["reminded"][order.id] = rec
                self._save()
                sent += 1
                time.sleep(REMIND_PAUSE)
        return sent

    def _remind(self, order) -> bool:
        from Utils import cardinal_tools
        try:
            chat = self.c.account.get_chat_by_name(order.buyer_username)
            chat_id = chat.id if chat else order.chat_id
            text = cardinal_tools.format_order_text(str(self.get("confirmReminderText")), order)
            ok = bool(self.c.send_message(chat_id, text, order.buyer_username))
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            ok = False
        if ok:
            logger.info(f"Mini App: напоминание подтвердить заказ #{order.id} отправлено {order.buyer_username}")
        else:
            logger.warning(f"Mini App: не удалось напомнить о заказе #{order.id}")
        return ok

    # ---------- отчёт за день ----------
    def build_report(self) -> str:
        from webapp.sales import REFUND
        today = datetime.date.today()
        orders = self.sales.today()
        sold = [o for o in orders if o.get("status") not in REFUND]
        refunds = len(orders) - len(sold)
        revenue: dict[str, float] = {}
        for o in sold:
            revenue[o["currency"]] = revenue.get(o["currency"], 0) + float(o.get("price") or 0)
        fmt = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", " ")
        money = " · ".join(f"{fmt(v)} {k}" for k, v in sorted(revenue.items(), key=lambda x: -x[1])) or "0 ₽"
        lines = [f"📊 <b>Отчёт за {today.day} {MONTHS[today.month - 1]}</b>", ""]
        lines.append(f"🛒 Заказов: <b>{len(sold)}</b>" + (f" · возвратов: {refunds}" if refunds else ""))
        lines.append(f"💰 Выручка: <b>{money}</b>")
        if sold:
            buyers = {o["buyer"] for o in sold}
            lines.append(f"👥 Покупателей: {len(buyers)}")
            top: dict[str, int] = {}
            for o in sold:
                top[o["description"]] = top.get(o["description"], 0) + 1
            title, n = max(top.items(), key=lambda x: x[1])
            lines.append(f"🏆 Чаще всего брали: {html.escape(title[:80])} — {n} шт.")
        waiting = sum(1 for o in orders if o.get("status") == "paid")
        if waiting:
            lines.append(f"⏳ Ждут подтверждения: {waiting}")
        b = getattr(self.c, "balance", None)
        if b is not None:
            parts = [f"{fmt(v)} {cur}" for v, cur in ((b.total_rub, "₽"), (b.total_usd, "$"), (b.total_eur, "€")) if v]
            if parts:
                lines.append(f"💳 Баланс: {' · '.join(parts)}")
        if self.stock is not None:
            try:
                a = self.stock.alerts()
                if a["empty"] or a["low"]:
                    bits = ([f"пусто — {a['empty']}"] if a["empty"] else []) + ([f"заканчивается — {a['low']}"] if a["low"] else [])
                    lines.append("📦 Склад: " + ", ".join(bits) + " (подробности в приложении → «Склад»)")
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
        return "\n".join(lines)

    def send_report(self, mark: bool = True) -> int:
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            raise ValueError("Telegram-бот выключен — отчёт некуда отправить.")
        text = self.build_report()
        sent = 0
        for user_id in list(getattr(tg, "authorized_users", {}) or {}):
            try:
                tg.bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
        if mark:
            with self._lock:
                self.state["report_sent"] = datetime.date.today().isoformat()
            self._save()
        logger.info(f"Mini App: отчёт за день отправлен ({sent} получ.)")
        return sent
