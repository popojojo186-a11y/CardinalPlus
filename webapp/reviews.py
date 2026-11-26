"""
Отзывы покупателей.

Откуда берутся: когда приходит отзыв (или его меняют/удаляют), Cardinal получает системное сообщение
в чате — по нему загружаем заказ и сохраняем отзыв. Старые отзывы можно догрузить кнопкой: по последним
завершённым заказам, по одному заказу с паузой.

Плохой отзыв (1–3 ★) — сразу сообщение в Telegram с кнопкой «Ответить на отзыв».
"""
from __future__ import annotations

import html
import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

PATH = os.path.join("storage", "cache", "webapp_reviews.json")
FETCH_PAUSE = 1.5
FETCH_MAX = 80
CB_REPLY = "cp_rv"            # callback кнопки «Ответить на отзыв»
STATE_REPLY = "cp_rv_text"    # состояние: бот ждёт текст ответа
# типы системных сообщений FunPay про отзывы (FunPayAPI.common.enums.MessageTypes)
REVIEW_TYPES = {"NEW_FEEDBACK", "FEEDBACK_CHANGED", "FEEDBACK_DELETED",
                "NEW_FEEDBACK_ANSWER", "FEEDBACK_ANSWER_CHANGED", "FEEDBACK_ANSWER_DELETED"}


class ReviewError(Exception):
    pass


class Reviews:
    def __init__(self, cardinal: Cardinal, automation, sales=None):
        self.c = cardinal
        self.auto = automation
        self.sales = sales
        self._lock = threading.RLock()
        data = self._load()
        self.items: dict[str, dict] = {k: v for k, v in (data.get("items") or {}).items() if isinstance(v, dict)}
        self.checked: dict[str, float] = dict(data.get("checked") or {})   # заказы без отзыва: когда проверяли
        self.alerted: dict[str, str] = dict(data.get("alerted") or {})     # о каком варианте отзыва уже сообщили
        self.job: dict | None = None
        self._installed = False

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
            cutoff = time.time() - 60 * 86400
            self.checked = {k: v for k, v in self.checked.items() if v > cutoff}
            data = {"items": self.items, "checked": self.checked, "alerted": self.alerted}
            try:
                os.makedirs(os.path.dirname(PATH), exist_ok=True)
                tmp = PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, PATH)
            except OSError:
                logger.debug("TRACEBACK", exc_info=True)

    # ---------- данные ----------
    def upsert(self, order, alert: bool = True) -> dict | None:
        """Сохраняет отзыв из заказа FunPay (объект FunPayAPI.types.Order). None — отзыва нет.
        alert=False — старый отзыв (догрузка), о нём в Telegram не сообщаем."""
        oid = str(order.id)
        r = getattr(order, "review", None)
        with self._lock:
            old = self.items.get(oid)
            if r is None or not getattr(r, "stars", None):
                self.checked[oid] = time.time()
                if old is not None:
                    old["deleted"] = True
                    old["updated"] = int(time.time())
                    self._save()
                return None
            item = {
                "order_id": oid, "stars": int(r.stars), "text": r.text or "", "reply": r.reply or "",
                "buyer": getattr(order, "buyer_username", None) or getattr(r, "author", None) or "",
                "buyer_id": getattr(order, "buyer_id", None),
                "chat_id": getattr(order, "chat_id", None),
                "title": getattr(order, "title", None) or "",
                "game": getattr(getattr(getattr(order, "subcategory", None), "category", None), "name", "") or "",
                "sum": getattr(order, "sum", None), "currency": str(getattr(order, "currency", "") or ""),
                "first_seen": (old or {}).get("first_seen") or int(time.time()),
                "updated": int(time.time()), "deleted": False,
            }
            changed = old is None or any(old.get(k) != item[k] for k in ("stars", "text", "reply", "deleted"))
            self.items[oid] = item
            self.checked.pop(oid, None)
            self._save()
        if changed and alert:
            self._maybe_alert(item)
        return item

    def list(self, flt: str = "", q: str = "") -> dict:
        with self._lock:
            items = [dict(v) for v in self.items.values() if not v.get("deleted")]
        items.sort(key=lambda x: -(x.get("first_seen") or 0))
        total = len(items)
        stars = {n: sum(1 for i in items if i["stars"] == n) for n in range(1, 6)}
        avg = round(sum(i["stars"] for i in items) / total, 2) if total else None
        no_reply = sum(1 for i in items if not i["reply"])
        bad = sum(1 for i in items if i["stars"] <= 3)
        month_ago = time.time() - 30 * 86400
        recent = [i for i in items if (i.get("first_seen") or 0) >= month_ago]
        if flt == "bad":
            items = [i for i in items if i["stars"] <= 3]
        elif flt == "noreply":
            items = [i for i in items if not i["reply"]]
        elif flt in ("1", "2", "3", "4", "5"):
            items = [i for i in items if i["stars"] == int(flt)]
        q = (q or "").strip().lower()
        if q:
            items = [i for i in items if q in f"{i['buyer']} {i['text']} {i['title']} {i['order_id']}".lower()]
        return {"items": items[:300], "total": total, "stars": stars, "avg": avg, "no_reply": no_reply, "bad": bad,
                "month": {"count": len(recent),
                          "avg": round(sum(i["stars"] for i in recent) / len(recent), 2) if recent else None},
                "job": self.job}

    def by_buyer(self) -> dict[str, dict]:
        """Ник (lower) -> {"count", "avg", "bad"} — для списка покупателей."""
        out: dict[str, dict] = {}
        with self._lock:
            for i in self.items.values():
                if i.get("deleted") or not i.get("buyer"):
                    continue
                r = out.setdefault(i["buyer"].lower(), {"count": 0, "sum": 0, "bad": 0})
                r["count"] += 1
                r["sum"] += i["stars"]
                r["bad"] += i["stars"] <= 3
        for r in out.values():
            r["avg"] = round(r.pop("sum") / r["count"], 1)
        return out

    # ---------- ответы ----------
    def reply(self, order_id: str, text: str) -> dict:
        order_id = str(order_id).lstrip("#")
        text = (text or "").strip()
        if not text:
            raise ReviewError("Пустой ответ.")
        if len(text) > 999:
            raise ReviewError("Ответ слишком длинный: FunPay принимает до 999 символов.")
        with self._lock:
            if order_id not in self.items:
                raise ReviewError("Отзыв не найден — обновите список.")
        try:
            self.c.account.send_review(order_id, text)
        except Exception as e:
            logger.debug("TRACEBACK", exc_info=True)
            why = getattr(e, "error_message", None)
            raise ReviewError(f"FunPay не принял ответ{': ' + str(why) if why else ''}. Попробуйте ещё раз чуть позже.")
        with self._lock:
            self.items[order_id]["reply"] = text
            self.items[order_id]["updated"] = int(time.time())
            self._save()
        logger.info(f"Mini App: ответ на отзыв к заказу #{order_id} опубликован.")
        return dict(self.items[order_id])

    def delete_reply(self, order_id: str) -> dict:
        order_id = str(order_id).lstrip("#")
        with self._lock:
            if order_id not in self.items:
                raise ReviewError("Отзыв не найден — обновите список.")
        try:
            self.c.account.delete_review(order_id)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            raise ReviewError("FunPay не удалил ответ. Попробуйте ещё раз чуть позже.")
        with self._lock:
            self.items[order_id]["reply"] = ""
            self.items[order_id]["updated"] = int(time.time())
            self._save()
        return dict(self.items[order_id])

    # ---------- догрузка по последним заказам ----------
    def start_fetch(self, orders: list[dict], limit: int = 40) -> dict:
        limit = max(1, min(FETCH_MAX, int(limit or 40)))
        with self._lock:
            if self.job and self.job.get("running"):
                return self.job
            todo = [o["id"] for o in orders if o.get("status") == "closed"
                    and str(o["id"]) not in self.items and str(o["id"]) not in self.checked][:limit]
            self.job = {"running": True, "done": 0, "total": len(todo), "found": 0, "started": int(time.time())}
            job = self.job
        threading.Thread(target=self._run_fetch, args=(job, todo), daemon=True, name="webapp-reviews").start()
        return job

    def _run_fetch(self, job: dict, ids: list[str]) -> None:
        try:
            for oid in ids:
                try:
                    order = self.c.account.get_order(str(oid).lstrip("#"))
                    if self.upsert(order, alert=False) is not None:
                        job["found"] += 1
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
                job["done"] += 1
                time.sleep(FETCH_PAUSE)
        finally:
            job["running"] = False
            job["ended"] = int(time.time())

    # ---------- события и Telegram ----------
    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        if hasattr(self.c, "new_message_handlers"):
            def on_new_message(cardinal, event):
                self.on_message(event.message)
            on_new_message.plugin_uuid = None
            self.c.new_message_handlers.append(on_new_message)
        self._install_telegram()

    def on_message(self, m) -> None:
        mtype = getattr(getattr(m, "type", None), "name", None)
        if mtype not in REVIEW_TYPES or getattr(m, "i_am_buyer", False):
            return

        def work():
            try:
                order = self.c.get_order_from_object(m)  # тот же запрос, что делает Cardinal для автоответа
                if order is not None:
                    self.upsert(order)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
        threading.Thread(target=work, daemon=True, name="webapp-review").start()

    def _maybe_alert(self, item: dict) -> None:
        if item["stars"] > 3 or not self.auto.flag("badReviewAlert"):
            return
        key = f"{item['stars']}|{item['text']}"
        with self._lock:
            if self.alerted.get(item["order_id"]) == key:
                return
            self.alerted[item["order_id"]] = key
            self._save()
        tg = getattr(self.c, "telegram", None)
        if tg is None:
            return
        try:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("✍️ Ответить на отзыв", callback_data=f"{CB_REPLY}:{item['order_id']}"))
            kb.add(InlineKeyboardButton("🌐 Заказ на FunPay", url=f"https://funpay.com/orders/{item['order_id']}/"))
        except Exception:
            kb = None
        text = (f"⚠️ <b>Плохой отзыв {'★' * item['stars']}{'☆' * (5 - item['stars'])}</b>\n"
                f"👤 {html.escape(item['buyer'] or 'Покупатель')} · заказ <code>#{item['order_id']}</code>\n"
                + (f"📦 {html.escape(item['title'][:120])}\n" if item["title"] else "")
                + f"\n«{html.escape(item['text'][:700]) or 'без текста'}»"
                + (f"\n\n💬 Ваш ответ: {html.escape(item['reply'][:300])}" if item["reply"] else ""))
        for user_id in list(getattr(tg, "authorized_users", {}) or {}):
            try:
                tg.bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)

    def _install_telegram(self) -> None:
        tg = getattr(self.c, "telegram", None)
        if tg is None or not hasattr(tg, "cbq_handler"):
            return
        bot = tg.bot

        def ask(call):
            if call.from_user.id not in tg.authorized_users:
                return
            order_id = call.data.split(":", 1)[1]
            with self._lock:
                item = self.items.get(order_id)
            if item is None:
                bot.answer_callback_query(call.id, "Отзыв не найден.", show_alert=True)
                return
            msg = bot.send_message(call.message.chat.id, f"✍️ Напишите ответ на отзыв к заказу #{order_id}.\n"
                                                         f"Он появится под отзывом на FunPay (до 999 символов).\n"
                                                         f"Передумали — отправьте «-».")
            tg.set_state(call.message.chat.id, msg.id, call.from_user.id, STATE_REPLY, {"order_id": order_id})
            bot.answer_callback_query(call.id)

        def got_text(message):
            state = tg.get_state(message.chat.id, message.from_user.id) or {}
            order_id = (state.get("data") or {}).get("order_id")
            tg.clear_state(message.chat.id, message.from_user.id, True)
            if not order_id or (message.text or "").strip() == "-":
                bot.reply_to(message, "Хорошо, ответ не отправлен.")
                return
            try:
                self.reply(order_id, message.text)
                bot.reply_to(message, f"✅ Ответ на отзыв к заказу #{order_id} опубликован.")
            except ReviewError as e:
                bot.reply_to(message, f"❌ {e}")

        tg.cbq_handler(ask, lambda c: str(getattr(c, "data", "")).startswith(f"{CB_REPLY}:"))
        tg.msg_handler(got_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, STATE_REPLY))
