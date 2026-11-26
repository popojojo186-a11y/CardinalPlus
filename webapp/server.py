"""
HTTP-сервер Mini App: отдаёт фронтенд (webapp/static) и JSON API.
Работает в отдельном потоке внутри Cardinal, слушает только 127.0.0.1 — снаружи доступен через туннель.
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import mimetypes
import os
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse, parse_qs

from http.cookies import SimpleCookie

from webapp import plugin_api, plus_updater, sessions
from webapp import version as plus_version
from webapp.auth import AuthError, validate_init_data
from webapp.lots import LotsError, LotsService
from webapp.chats import ChatError, ChatsService
from webapp.stock import StockError, StockService
from webapp.sales import SalesHistory, summarize
from webapp.automation import AutomationService
from webapp.audit import Audit
from webapp.guard import Guard
from webapp.inbox import Inbox
from webapp.reviews import Reviews, ReviewError
from webapp.business import Business
from webapp.schedule import Schedule
from webapp import backup as backup_mod

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 1024 * 1024
MAX_BACKUP_BODY = 90 * 1024 * 1024   # резервная копия приходит файлом в base64
BACKUP_ROUTES = ("/api/backup/restore", "/api/backup/inspect")

# Встроенные переключатели Cardinal, которые можно менять из приложения: (секция, опция, название, описание)
CORE_TOGGLES = [
    ("Автоматизация", [
        ("FunPay", "autoRaise", "Автоподнятие лотов", ""),
        ("FunPay", "autoResponse", "Автоответчик", "Ответы на команды покупателей"),
        ("FunPay", "autoDelivery", "Автовыдача", "Выдача товара после оплаты"),
        ("FunPay", "multiDelivery", "Мультивыдача", "Несколько товаров в одном заказе"),
        ("FunPay", "autoRestore", "Восстановление лотов", "Включать лоты обратно после продажи"),
        ("FunPay", "autoDisable", "Деактивация лотов", "Выключать лоты, когда закончились товары"),
    ]),
    ("Сообщения", [
        ("Greetings", "sendGreetings", "Приветствие", "Приветственное сообщение новым покупателям"),
        ("Greetings", "onlyNewChats", "Только новые чаты", "Приветствовать только тех, кто пишет впервые"),
        ("OrderConfirm", "sendReply", "Ответ на подтверждение", "Сообщение после подтверждения заказа"),
        ("CardinalPlus", "confirmReminder", "Напоминание подтвердить заказ", "Если покупатель долго не подтверждает заказ"),
        ("FunPay", "keepSentMessagesUnread", "Не читать чаты", "Оставлять сообщения непрочитанными"),
        ("FunPay", "oldMsgGetMode", "Старый режим сообщений", "Получение сообщений через чаты"),
    ]),
    ("Контроль и уведомления", [
        ("CardinalPlus", "waitReply", "Покупатель ждёт ответа", "Напомнить в Telegram, если вы долго не отвечаете"),
        ("CardinalPlus", "badReviewAlert", "Плохой отзыв", "Сразу сообщать об отзывах 1–3 ★ с кнопкой «Ответить»"),
        ("CardinalPlus", "watchdog", "Сторож", "Сообщить в Telegram, если Cardinal потерял связь с FunPay"),
        ("CardinalPlus", "quietHours", "Тихие часы", "Ночью уведомления без звука или утром одним сообщением"),
    ]),
    ("Отчёты", [
        ("CardinalPlus", "dailyReport", "Отчёт за день в Telegram", "Каждый вечер: заказы, выручка, баланс, склад"),
    ]),
    ("Ответы на отзывы", [
        ("ReviewReply", f"star{n}Reply", f"Отзыв {'★' * n}", "") for n in range(5, 0, -1)
    ]),
    ("Чёрный список", [
        ("BlockList", "blockDelivery", "Не выдавать товар", ""),
        ("BlockList", "blockResponse", "Не отвечать на команды", ""),
        ("BlockList", "blockNewMessageNotification", "Без уведомлений о сообщениях", ""),
        ("BlockList", "blockNewOrderNotification", "Без уведомлений о заказах", ""),
        ("BlockList", "blockCommandNotification", "Без уведомлений о командах", ""),
    ]),
]
ALLOWED_TOGGLES = {(s, o) for _, items in CORE_TOGGLES for s, o, *_ in items}

# Переменные, которые Cardinal подставляет в тексты (как в меню бота)
_V_COMMON = [("$date", "дата ДД.ММ.ГГГГ"), ("$date_text", "дата «1 января»"), ("$time", "время ЧЧ:ММ"),
             ("$username", "ник покупателя")]
_V_ORDER = [("$order_id", "номер заказа"), ("$order_link", "ссылка на заказ"), ("$order_title", "название заказа"),
            ("$game", "игра"), ("$category", "подкатегория")]
_V_MEDIA = [("$photo=", "фото: ID из /upload_chat_img"), ("$sleep=", "пауза в секундах")]

# Текстовые настройки, привязанные к переключателям: (секция, переключатель) -> поля
CORE_TEXTS = {
    ("Greetings", "sendGreetings"): [
        {"option": "greetingsText", "type": "textarea", "label": "Текст приветствия",
         "vars": _V_COMMON + [("$message_text", "сообщение покупателя"), ("$chat_name", "название чата")] + _V_MEDIA},
        {"option": "greetingsCooldown", "type": "number", "label": "Повторять не чаще, чем раз в N дней",
         "hint": "Одному и тому же покупателю приветствие придёт снова только через это время.", "min": 0},
    ],
    ("OrderConfirm", "sendReply"): [
        {"option": "replyText", "type": "textarea", "label": "Текст после подтверждения заказа",
         "vars": _V_COMMON + _V_ORDER + _V_MEDIA},
    ],
    ("CardinalPlus", "confirmReminder"): [
        {"option": "confirmReminderText", "type": "textarea", "label": "Текст напоминания",
         "hint": "Бот напишет его в чат покупателю, который оплатил, но ещё не подтвердил заказ. Максимум 2 раза на заказ.",
         "vars": _V_COMMON + _V_ORDER},
        {"option": "confirmReminderHours", "type": "number", "label": "Через сколько часов после оплаты напомнить", "min": 1},
        {"option": "confirmReminderRepeat", "type": "number", "label": "Напомнить ещё раз через N часов",
         "hint": "0 — напомнить только один раз. Заказы старше 3 дней бот не трогает.", "min": 0},
    ],
    ("CardinalPlus", "dailyReport"): [
        {"option": "dailyReportTime", "type": "time", "label": "Во сколько присылать",
         "hint": "Отчёт придёт всем, кто вошёл в Telegram-бота Cardinal."},
        {"option": "reportNow", "type": "button", "label": "Прислать отчёт сейчас", "action": "report_now"},
    ],
    ("CardinalPlus", "waitReply"): [
        {"option": "waitReplyMinutes", "type": "number", "label": "Через сколько минут напомнить", "min": 1,
         "hint": "Ответом считается сообщение с сайта FunPay, из приложения или из Telegram-бота. "
                 "Автоприветствие, автовыдача и команды автоответчика — нет. Напоминание приходит один раз."},
    ],
    ("CardinalPlus", "watchdog"): [
        {"option": "watchdogMinutes", "type": "number", "label": "Сообщить, если связи нет дольше, минут", "min": 2,
         "hint": "Например, устарел golden_key, FunPay недоступен или пропал интернет. Когда связь вернётся, "
                 "придёт ещё одно сообщение. Если выключится сам компьютер, сообщить будет некому."},
    ],
    ("CardinalPlus", "quietHours"): [
        {"option": "quietFrom", "type": "time", "label": "С"},
        {"option": "quietTo", "type": "time", "label": "До"},
        {"option": "quietMode", "type": "select", "label": "Что делать с уведомлениями",
         "options": [["silent", "Присылать без звука"], ["hold", "Не присылать, а утром — одним сообщением"]],
         "hint": "Сообщения сторожа, о плохих отзывах и ответы на ваши команды приходят всегда, но без звука."},
    ],
    **{("ReviewReply", f"star{n}Reply"): [
        {"option": f"star{n}ReplyText", "type": "textarea", "label": f"Ответ на отзыв {'★' * n}",
         "hint": "Ответ публикуется под отзывом на FunPay.",
         "vars": _V_COMMON + _V_ORDER + [("$order_params", "параметры заказа")]},
    ] for n in range(1, 6)},
}
ALLOWED_TEXTS = {(s, f["option"]): f for (s, _), fields in CORE_TEXTS.items() for f in fields if f["type"] != "button"}


def read_cookie(headers, name: str) -> str:
    raw = headers.get("Cookie", "")
    if not raw:
        return ""
    try:
        c = SimpleCookie()
        c.load(raw)
        return c[name].value if name in c else ""
    except Exception:
        return ""


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class TTLCache:
    def __init__(self):
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float, producer: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._data.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        value = producer()
        with self._lock:
            self._data[key] = (time.time(), value)
        return value

    def drop(self, key: str):
        with self._lock:
            self._data.pop(key, None)


class WebApp:
    def __init__(self, cardinal: Cardinal, host: str, port: int):
        self.cardinal = cardinal
        self.host = host
        self.port = port
        self.cache = TTLCache()
        self.public_url: str | None = None
        self.httpd: ThreadingHTTPServer | None = None
        # (метод, regex пути) -> обработчик(user, match, query, body)
        self.routes: list[tuple[str, re.Pattern, Callable]] = []
        self.lots = LotsService(cardinal)
        self.chats = ChatsService(cardinal)
        self.chats.install()
        self.stock = StockService(cardinal)
        self.stock.install()
        self.sales = SalesHistory(cardinal, self._order_to_dict)
        self.automation = AutomationService(cardinal, self.sales, self.stock)
        self.automation.start()
        self.audit = Audit(cardinal)
        # понятные названия настроек для журнала действий
        for _, items in CORE_TOGGLES:
            for s, o, label, _hint in items:
                self.audit.labels[(s, o)] = label
                for f in CORE_TEXTS.get((s, o), []):
                    self.audit.labels[(s, f["option"])] = f"{label}: {f['label'].lower()}"
        from webapp.guard import NOTIFICATION_TYPES
        self.audit.notification_names = {code: name for code, name, _ in NOTIFICATION_TYPES}
        self.guard = Guard(cardinal, self.automation, self.audit)
        self.guard.start()
        self.inbox = Inbox(cardinal, self.automation)
        self.inbox.install()
        self.inbox.start()
        self.chats.on_fetch = lambda chat_id, name, messages: self.inbox.archive(messages, chat_id, name)
        self.reviews = Reviews(cardinal, self.automation, self.sales)
        self.reviews.install()
        self.business = Business()
        self.schedule = Schedule(self.lots, self.audit)
        self.schedule.start()
        self._register_routes()

    # ---------- инфраструктура ----------
    def route(self, method: str, pattern: str):
        def decorator(func):
            self.routes.append((method, re.compile(f"^{pattern}$"), func))
            return func
        return decorator

    def start(self):
        app = self

        class Handler(_Handler):
            webapp = app

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="webapp-http").start()
        logger.info(f"Mini App: веб-сервер запущен на http://{self.host}:{self.port}")

    def authorize(self, headers) -> dict:
        tg = self.cardinal.telegram
        if tg is None:
            raise ApiError("Telegram-бот выключен в настройках Cardinal.", 503)
        init_data = headers.get("X-Init-Data", "")
        if init_data:
            try:
                user = validate_init_data(init_data, self.cardinal.MAIN_CFG["Telegram"]["token"])
            except AuthError as e:
                raise ApiError(f"Нет доступа ({e}). Откройте приложение через бота.", 401)
            user["via"] = "telegram"
        else:
            # Браузер: cookie-сессия. Свой заголовок X-CP не даёт чужим сайтам слать запросы от имени пользователя.
            if headers.get("X-CP") != "1":
                raise ApiError("Нет доступа.", 401)
            user_id = sessions.get_session_user(read_cookie(headers, sessions.COOKIE_NAME))
            if user_id is None:
                raise ApiError("Сессия истекла. Отправьте боту /web, чтобы войти снова.", 401)
            user = {"id": user_id, "via": "browser"}
        if user["id"] not in tg.authorized_users:
            raise ApiError("Вы не авторизованы. Отправьте боту /start и введите пароль Cardinal.", 403)
        return user

    def login_link(self, user_id: int, host: str | None = None) -> str:
        base = self.public_url or (f"https://{host}" if host else f"http://{self.host}:{self.port}")
        return f"{base}/login?t={sessions.create_login_token(user_id)}"

    # ---------- данные ----------
    @staticmethod
    def _money(value) -> float:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return 0.0

    def _order_to_dict(self, o) -> dict:
        return {
            "id": o.id,
            "description": o.description,
            "price": o.price,
            "currency": str(o.currency),
            "amount": o.amount,
            "buyer": o.buyer_username,
            "buyer_id": o.buyer_id,
            "chat_id": o.chat_id,
            "status": o.status.name.lower(),
            "date": o.date.isoformat() if o.date else None,
            "subcategory": o.subcategory_name,
        }

    def _load_orders(self) -> list[dict]:
        def produce():
            _, orders, *_ = self.cardinal.account.get_sales()
            return [self._order_to_dict(o) for o in orders]
        return self.cache.get("orders", 30, produce)

    def _account_info(self) -> dict:
        acc = self.cardinal.account
        avatar = None
        profile = getattr(self.cardinal, "profile", None) or getattr(self.cardinal, "tg_profile", None)
        photo = getattr(profile, "profile_photo", None) if profile else None
        # У FunPay без загруженного фото стоит стандартная заглушка — её не показываем, остаётся буква
        if photo and photo.startswith("https://") and "/img/layout/avatar" not in photo:
            avatar = photo
        return {"id": getattr(acc, "id", None), "username": getattr(acc, "username", None), "avatar": avatar,
                "profile_link": f"https://funpay.com/users/{acc.id}/" if getattr(acc, "id", None) else None}

    def _plugin_entry(self, uuid: str, p) -> dict:
        spec = plugin_api.get_webapp_spec(p.plugin) or {}
        return {
            "uuid": uuid,
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "credits": p.credits,
            "enabled": p.enabled,
            "pinned": p.pinned,
            "icon": spec.get("icon") or "🧩",
            "has_ui": bool(spec.get("settings") or plugin_api.has_page(spec)),
            "has_page": plugin_api.has_page(spec),
            "has_tg_settings": bool(p.settings_page),
            "commands": dict(p.commands),
            "warnings": self._plugin_warnings(uuid),
            "pending_update": self._pending_update(uuid),
            "license": self._plugin_license(p),
        }

    def _plugin_license(self, p):
        """Лицензия плагина из магазина (блок Sqeye Shop): {"ok", "text", "shop"} или None, если её нет."""
        check = getattr(p.plugin, "sqeye_license", None)
        if not callable(check):
            return None
        try:
            ok, text = check(self.cardinal)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            ok, text = False, "не удалось проверить лицензию"
        return {"ok": bool(ok), "text": str(text), "shop": str(getattr(p.plugin, "SQEYE_SHOP", "") or ""),
                "dev": not getattr(p.plugin, "SQEYE_LICENSE", "")}

    @staticmethod
    def _pending_update(uuid: str):
        from webapp import plugin_installer
        return plugin_installer.PENDING.get(uuid)

    @staticmethod
    def _plugin_warnings(uuid: str) -> list:
        """Замечания по плагину: одинаковые команды с другими плагинами, ошибки в хэндлерах бота."""
        try:
            from Utils import command_guard
            return command_guard.plugin_warnings(uuid)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            return []

    def _get_plugin(self, uuid: str):
        p = self.cardinal.plugins.get(uuid)
        if p is None:
            raise ApiError("Плагин не найден.", 404)
        return p

    # ---------- маршруты ----------
    def _register_routes(self):
        crd = self.cardinal

        @self.route("POST", "/api/login-link")
        def login_link(user, m, q, body):
            return {"url": self.login_link(user["id"], q.get("_host"))}

        @self.route("GET", "/api/me")
        def me(user, m, q, body):
            acc = crd.account
            return {
                "user": {"id": user["id"], "first_name": user.get("first_name"), "username": user.get("username"),
                         "via": user.get("via")},
                "account": self._account_info(),
                "version": crd.VERSION,
                "plus_version": plus_version.VERSION,
                "keep_alive": bool(__import__("webapp")._state.get("front")),
                "uptime": int(time.time()) - crd.start_time,
            }

        @self.route("GET", "/api/plus/update")
        def plus_update_status(user, m, q, body):
            """Обновление Cardinal Plus: текущая и последняя версия (с ?check=1 — спросить GitHub прямо сейчас)."""
            return plus_updater.check(force=True) if q.get("check") else plus_updater.status()

        @self.route("POST", "/api/plus/update")
        def plus_update_install(user, m, q, body):
            st = plus_updater.status()
            if not st["available"]:
                raise ApiError(st["error"] or f"У вас последняя версия Cardinal Plus {plus_version.VERSION}.")
            try:
                plus_updater.install_async()
            except plus_updater.UpdateError as e:
                raise ApiError(str(e))
            logger.info(f"Mini App: {user['id']} обновляет Cardinal Plus {plus_version.VERSION} → {st['latest']['version']}")
            return plus_updater.status()

        @self.route("GET", "/api/dashboard")
        def dashboard(user, m, q, body):
            b = crd.balance
            balance = None
            if b is not None:
                balance = {
                    "rub": self._money(b.total_rub), "rub_available": self._money(b.available_rub),
                    "usd": self._money(b.total_usd), "usd_available": self._money(b.available_usd),
                    "eur": self._money(b.total_eur), "eur_available": self._money(b.available_eur),
                }
            lots_total = lots_active = None
            try:
                if crd.profile is not None:
                    lots_total = len(crd.profile.get_lots())
                if crd.curr_profile is not None:
                    lots_active = len(crd.curr_profile.get_lots())
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)

            today = {"count": 0, "sum": {}}
            paid_now = 0
            orders_error = None
            today_date = datetime.date.today()
            week = [{"date": (today_date - datetime.timedelta(days=i)).isoformat(), "count": 0, "sum": {}}
                    for i in range(6, -1, -1)]
            week_index = {d["date"]: d for d in week}
            recent = []
            today_orders = []
            try:
                all_orders = self._load_orders()
                bl = set(crd.blacklist)
                recent = [{**o, "blacklisted": o["buyer"] in bl} for o in all_orders[:5]]
                for o in all_orders:
                    if o["status"] == "paid":
                        paid_now += 1
                    if not o["date"] or o["status"] in ("refunded", "partially_refunded"):
                        continue
                    day = datetime.datetime.fromisoformat(o["date"]).date()
                    bucket = week_index.get(day.isoformat())
                    if bucket is not None:
                        bucket["count"] += 1
                        bucket["sum"][o["currency"]] = round(bucket["sum"].get(o["currency"], 0) + o["price"], 2)
                    if day == today_date:
                        today["count"] += 1
                        today["sum"][o["currency"]] = round(today["sum"].get(o["currency"], 0) + o["price"], 2)
                        today_orders.append(o)
            except Exception as e:
                orders_error = str(e) or e.__class__.__name__
                logger.debug("TRACEBACK", exc_info=True)
            if self.business.has_costs():
                today["profit"] = self.business.profit(today_orders)

            upd = plus_updater.status()
            return {
                "plus_update": {"available": upd["available"], "version": (upd["latest"] or {}).get("version")},
                "balance": balance,
                "lots": {"total": lots_total, "active": lots_active},
                "orders": {"today": today, "paid": paid_now, "error": orders_error, "week": week, "recent": recent},
                "modules": {
                    "autoRaise": crd.autoraise_enabled,
                    "autoResponse": crd.autoresponse_enabled,
                    "autoDelivery": crd.autodelivery_enabled,
                },
                "plugins": {"total": len(crd.plugins), "enabled": sum(1 for p in crd.plugins.values() if p.enabled)},
                "stock": self.stock.alerts(),
                "uptime": int(time.time()) - crd.start_time,
                "account": self._account_info(),
                "guard": self.guard.status(),
                "waiting": len(self.inbox.waiting_info()),
                "plan": self.business.plan,
                "reviews": {k: v for k, v in self.reviews.list().items() if k in ("avg", "total", "bad", "no_reply")},
            }

        @self.route("POST", "/api/balance/refresh")
        def refresh_balance(user, m, q, body):
            try:
                crd.balance = crd.get_balance()
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError("Не удалось обновить баланс, попробуйте позже.", 424)
            return dashboard(user, m, q, body)

        @self.route("GET", "/api/orders")
        def orders(user, m, q, body):
            if q.get("refresh"):
                self.cache.drop("orders")
            try:
                items = self._load_orders()
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError("Не удалось загрузить заказы с FunPay.", 424)
            counts = {"": len(items)}
            for o in items:
                counts[o["status"]] = counts.get(o["status"], 0) + 1
            status = q.get("status")
            if status:
                items = [o for o in items if o["status"] == status]
            bl = set(crd.blacklist)
            items = [{**o, "blacklisted": o["buyer"] in bl} for o in items]
            return {"orders": items, "counts": counts}

        # ---------- склад автовыдачи ----------
        def stock_call(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except StockError as e:
                raise ApiError(str(e))

        @self.route("GET", "/api/stock")
        def stock_overview(user, m, q, body):
            return stock_call(self.stock.overview)

        @self.route("GET", "/api/stock/file")
        def stock_file(user, m, q, body):
            return stock_call(self.stock.items, q.get("name") or "", q.get("q") or "")

        @self.route("POST", "/api/stock/file")
        def stock_file_change(user, m, q, body):
            s, action, name = self.stock, str(body.get("action") or ""), str(body.get("name") or "")
            if action == "create":
                return stock_call(s.create, name)
            if action == "add":
                return stock_call(s.add, name, str(body.get("text") or ""), body.get("dedupe", True) is not False)
            if action == "remove":
                index = body.get("index")
                index = int(index) if isinstance(index, (int, float)) and not isinstance(index, bool) else -1
                return stock_call(s.remove, name, index, str(body.get("text") or ""))
            if action == "clear":
                return stock_call(s.clear, name)
            if action == "delete":
                return stock_call(s.delete, name)
            if action == "low":
                return stock_call(s.set_low, name, body.get("value"))
            raise ApiError("Неизвестное действие.")

        @self.route("POST", "/api/stock/lot")
        def stock_lot_change(user, m, q, body):
            s, action, title = self.stock, str(body.get("action") or ""), str(body.get("title") or "")
            if action == "link":
                return stock_call(s.link, title, body.get("file") or None, body.get("new_file") or None,
                                  body.get("response") or None)
            if action == "update":
                return stock_call(s.update, title, {k: body[k] for k in ("file", "response", "disabled", "multi_off") if k in body})
            if action == "unlink":
                return stock_call(s.unlink, title)
            raise ApiError("Неизвестное действие.")

        # ---------- чаты ----------
        def chats_call(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ChatError as e:
                raise ApiError(str(e))

        @self.route("GET", "/api/chats")
        def chats_list(user, m, q, body):
            result = chats_call(self.chats.list)
            waiting = self.inbox.waiting_info()
            for c in result["chats"]:
                c["waiting"] = waiting.get(c["id"])
            result["waiting"] = sum(1 for c in result["chats"] if c["waiting"] is not None)
            return result

        @self.route("GET", "/api/chats/search")
        def chats_search(user, m, q, body):
            try:
                orders = self._load_orders()
            except Exception:
                orders = []
            try:
                return self.inbox.search(q.get("q") or "", orders)
            except ValueError as e:
                raise ApiError(str(e))

        @self.route("GET", "/api/chats/archive")
        def chats_archive(user, m, q, body):
            return self.inbox.archive_stats()

        @self.route("POST", "/api/chats/index")
        def chats_index(user, m, q, body):
            return {"job": self.inbox.start_index(body.get("count") or 30)}

        @self.route("GET", "/api/chats/templates")
        def chat_templates(user, m, q, body):
            return {"templates": self.chats.templates()}

        @self.route("POST", "/api/chats/templates")
        def chat_templates_change(user, m, q, body):
            index = body.get("index")
            index = int(index) if isinstance(index, (int, float)) and not isinstance(index, bool) else None
            items = chats_call(self.chats.change_templates, str(body.get("action") or ""), body.get("text"), index)
            return {"templates": items}

        @self.route("GET", r"/api/chats/(?P<chat_id>\d{1,15})")
        def chat_history(user, m, q, body):
            since = q.get("since") or "0"
            since = int(since) if since.isdigit() else 0
            return chats_call(self.chats.history, int(m["chat_id"]), since, q.get("read") == "1")

        @self.route("POST", r"/api/chats/(?P<chat_id>\d{1,15})/send")
        def chat_send(user, m, q, body):
            result = chats_call(self.chats.send, int(m["chat_id"]), str(body.get("text") or ""))
            logger.info(f"Mini App: {user['id']} ответил в чат {m['chat_id']}")
            return result

        @self.route("POST", r"/api/chats/(?P<chat_id>\d{1,15})/image")
        def chat_image(user, m, q, body):
            raw = str(body.get("image") or "")
            if "," in raw[:100]:
                raw = raw.split(",", 1)[1]  # «data:image/jpeg;base64,....»
            try:
                data = base64.b64decode(raw, validate=True)
            except (ValueError, TypeError):
                raise ApiError("Картинка повреждена — попробуйте выбрать её ещё раз.")
            result = chats_call(self.chats.send_image, int(m["chat_id"]), data)
            logger.info(f"Mini App: {user['id']} отправил картинку в чат {m['chat_id']}")
            return result

        @self.route("GET", r"/api/chats/(?P<chat_id>\d{1,15})/buyer")
        def chat_buyer(user, m, q, body):
            info = self.chats.info(int(m["chat_id"]))
            name = info["name"]
            result = {"name": name, "blacklisted": bool(name and name in crd.blacklist),
                      "profile": f"https://funpay.com/users/{info['interlocutor_id']}/" if info["interlocutor_id"] else None,
                      "orders": None, "count": 0, "sum": {}}
            if not name:
                return result
            try:
                orders = [o for o in self._load_orders() if o["buyer"] == name]
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                return result
            total: dict[str, float] = {}
            for o in orders:
                if o["status"] not in ("refunded", "partially_refunded"):
                    total[o["currency"]] = round(total.get(o["currency"], 0) + self._money(o["price"]), 2)
            result.update(orders=orders[:15], count=len(orders), sum=total)
            return result

        # ---------- лоты ----------
        def lots_call(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except LotsError as e:
                raise ApiError(str(e))
            except ApiError:
                raise
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError("Не удалось связаться с FunPay, попробуйте позже.", 424)

        @self.route("GET", "/api/lots")
        def lots_list(user, m, q, body):
            return lots_call(self.lots.list, refresh=bool(q.get("refresh")))

        @self.route("GET", r"/api/lots/(?P<lot_id>\d+)")
        def lot_details(user, m, q, body):
            return lots_call(self.lots.details, int(m["lot_id"]))

        @self.route("POST", r"/api/lots/(?P<lot_id>\d+)")
        def lot_update(user, m, q, body):
            price = body.get("price")
            if price is not None:
                try:
                    price = float(str(price).replace(",", "."))
                except ValueError:
                    raise ApiError("Некорректная цена.")
            active = body.get("active")
            active = None if active is None else bool(active)
            result = lots_call(self.lots.update_one, int(m["lot_id"]), price=price, active=active)
            logger.info(f"Mini App: {user['id']} изменил лот {m['lot_id']}: цена {result['price']}, активен {result['active']}")
            return result

        @self.route("POST", "/api/lots/bulk")
        def lots_bulk(user, m, q, body):
            ids = body.get("ids") or []
            if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
                raise ApiError("Некорректный список лотов.")
            job_id = lots_call(self.lots.start_bulk, list(dict.fromkeys(ids)), body.get("op") or {}, user["id"])
            return {"job": job_id}

        @self.route("GET", r"/api/lots/jobs/(?P<job>[0-9a-f]{16})")
        def lots_job(user, m, q, body):
            job = self.lots.jobs.get(m["job"])
            if not job:
                raise ApiError("Задача не найдена.", 404)
            return job

        @self.route("POST", "/api/lots/demo")
        def lots_demo(user, m, q, body):
            lots_call(self.lots.set_demo, bool(body.get("enabled")))
            logger.info(f"Mini App: {user['id']} {'включил' if self.lots.demo else 'выключил'} демо-режим лотов.")
            return {"ok": True, "demo": self.lots.demo}

        @self.route("POST", "/api/lots/subcategory")
        def lots_add_sub(user, m, q, body):
            try:
                sub_id = int(body.get("id"))
            except (TypeError, ValueError):
                raise ApiError("Укажите номер подкатегории.")
            lots_call(self.lots.add_subcategory, sub_id)
            return {"ok": True}

        @self.route("GET", r"/api/lots/(?P<lot_id>\d+)/copy")
        def lot_copy_info(user, m, q, body):
            return lots_call(self.lots.copy_info, int(m["lot_id"]))

        @self.route("POST", r"/api/lots/(?P<lot_id>\d+)/copy")
        def lot_copy(user, m, q, body):
            price = body.get("price")
            if price not in (None, ""):
                try:
                    price = float(str(price).replace(",", "."))
                except ValueError:
                    raise ApiError("Некорректная цена.")
            else:
                price = None
            title = body.get("title")
            result = lots_call(self.lots.copy, int(m["lot_id"]), None if title is None else str(title), price,
                               bool(body.get("active")))
            logger.info(f"Mini App: {user['id']} скопировал лот {m['lot_id']}")
            return result

        @self.route("GET", "/api/lots/schedule")
        def lots_schedule(user, m, q, body):
            return self.schedule.state()

        @self.route("POST", "/api/lots/schedule")
        def lots_schedule_change(user, m, q, body):
            action = body.get("action")
            try:
                if action == "save":
                    return self.schedule.save_rule(body.get("rule") or {})
                if action == "toggle":
                    return self.schedule.toggle(str(body.get("id") or ""), bool(body.get("enabled")))
                if action == "delete":
                    return self.schedule.delete(str(body.get("id") or ""))
            except ValueError as e:
                raise ApiError(str(e))
            raise ApiError("Неизвестное действие.")

        @self.route("GET", "/api/blacklist")
        def blacklist(user, m, q, body):
            return {"users": sorted(crd.blacklist, key=lambda x: x.lower())}

        @self.route("POST", "/api/blacklist/(?P<action>add|remove)")
        def blacklist_change(user, m, q, body):
            from Utils import cardinal_tools
            nickname = str(body.get("nickname") or "").strip()
            if not nickname or len(nickname) > 64 or any(ch.isspace() for ch in nickname):
                raise ApiError("Укажите ник покупателя на FunPay — одним словом, без пробелов.")
            if m["action"] == "add":
                if nickname in crd.blacklist:
                    raise ApiError(f"{nickname} уже в чёрном списке.", 409)
                crd.blacklist.append(nickname)
            else:
                if nickname not in crd.blacklist:
                    raise ApiError(f"{nickname} нет в чёрном списке.", 404)
                crd.blacklist.remove(nickname)
            cardinal_tools.cache_blacklist(crd.blacklist)
            logger.info(f"Mini App: {user['id']} {'добавил в ЧС' if m['action'] == 'add' else 'убрал из ЧС'} {nickname}")
            return {"ok": True, "users": sorted(crd.blacklist, key=lambda x: x.lower())}

        @self.route("GET", "/api/settings")
        def get_settings(user, m, q, body):
            groups = []
            auto = self.automation
            plus = lambda s: s == "CardinalPlus"  # настройки Cardinal+ хранятся отдельно от _main.cfg
            for title, items in CORE_TOGGLES:
                groups.append({"title": title, "items": [
                    {"section": s, "option": o, "label": label, "hint": hint,
                     "value": auto.flag(o) if plus(s) else crd.MAIN_CFG[s].getboolean(o),
                     "fields": [
                         {**{k: v for k, v in f.items() if k != "vars"},
                          "vars": [list(x) for x in f.get("vars", [])],
                          "value": (auto.get(f["option"]) if f["type"] != "button" else None) if plus(s)
                          else crd.MAIN_CFG[s].get(f["option"], "")}
                         for f in CORE_TEXTS.get((s, o), []) if plus(s) or crd.MAIN_CFG.has_option(s, f["option"])
                     ]}
                    for s, o, label, hint in items if plus(s) or crd.MAIN_CFG.has_option(s, o)
                ]})
            return {"groups": groups}

        @self.route("POST", "/api/settings/text")
        def set_text(user, m, q, body):
            section, option = body.get("section"), body.get("option")
            field = ALLOWED_TEXTS.get((section, option))
            if field is not None and section == "CardinalPlus":
                try:
                    value = self.automation.set_text(option, body.get("value"))
                except ValueError as e:
                    raise ApiError(str(e))
                logger.info(f"Mini App: {user['id']} изменил {option}")
                return {"ok": True, "value": value}
            if field is None or not crd.MAIN_CFG.has_option(section, option):
                raise ApiError("Эту настройку нельзя менять из приложения.")
            value = body.get("value")
            if field["type"] == "number":
                try:
                    num = float(str(value).replace(",", "."))
                except (TypeError, ValueError):
                    raise ApiError("Нужно число.")
                if num < field.get("min", 0):
                    raise ApiError(f"Минимум {field.get('min', 0)}.")
                value = str(int(num) if num.is_integer() else num)
            else:
                value = "" if value is None else str(value).replace("\r\n", "\n")
                if len(value) > 4000:
                    raise ApiError("Слишком длинный текст (максимум 4000 символов).")
                if not value.strip() and section != "ReviewReply":
                    raise ApiError("Текст не может быть пустым.")
            crd.MAIN_CFG[section][option] = value
            crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")
            logger.info(f"Mini App: {user['id']} изменил {section}.{option}")
            return {"ok": True, "value": value}

        @self.route("POST", "/api/settings")
        def set_setting(user, m, q, body):
            section, option, value = body.get("section"), body.get("option"), bool(body.get("value"))
            if (section, option) not in ALLOWED_TOGGLES:
                raise ApiError("Эту настройку нельзя менять из приложения.")
            if section == "CardinalPlus":
                value = self.automation.set_flag(option, value)
                logger.info(f"Mini App: {user['id']} {'включил' if value else 'выключил'} {option}")
                return {"ok": True, "value": value}
            current = crd.MAIN_CFG[section].getboolean(option)
            if current != value:
                if (section, option) == ("FunPay", "oldMsgGetMode"):
                    crd.switch_msg_get_mode()
                else:
                    crd.MAIN_CFG[section][option] = "1" if value else "0"
                    crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")
                logger.info(f"Mini App: {user.get('username')} ({user['id']}) изменил {section}.{option} -> {int(value)}")
            return {"ok": True, "value": crd.MAIN_CFG[section].getboolean(option)}

        @self.route("POST", "/api/automation/action")
        def automation_action(user, m, q, body):
            if body.get("action") != "report_now":
                raise ApiError("Неизвестное действие.")
            try:
                sent = self.automation.send_report(mark=False)
            except ValueError as e:
                raise ApiError(str(e))
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError("Не удалось собрать отчёт — FunPay не ответил. Попробуйте через минуту.")
            return {"ok": True, "sent": sent}

        @self.route("GET", "/api/stats")
        def stats(user, m, q, body):
            days = q.get("days") or "30"
            days = int(days) if days.isdigit() and int(days) in (7, 30, 90, 365) else 30
            r = self.sales.request(days, refresh=q.get("refresh") == "1")
            if not r["ready"]:
                if r.get("error"):
                    raise ApiError(r["error"])
                return {"ready": False, "pages": r.get("pages", 0)}
            orders = r["orders"]
            bl = set(crd.blacklist)
            summary = summarize(orders, days)
            main = summary.get("currency") or "₽"
            lot_profit = self.business.lot_profits(orders, main)
            for lot in summary["top_lots"]:
                p = lot_profit.get(lot["title"]) or {}
                lot["profit"] = p.get("profit")
                lot["unit_cost"] = p.get("unit_cost")
            # себестоимость можно задать для любого товара за период, не только из топа
            titles = sorted({o.get("description") or "—" for o in orders if o.get("status") not in ("refunded", "partially_refunded")})
            return {"ready": True, "summary": summary, "partial": r["partial"],
                    "covered_from": r["covered_from"], "orders": [{**o, "blacklisted": o["buyer"] in bl} for o in orders],
                    "profit": self.business.profit(orders, main) if self.business.has_costs() else None,
                    "costs": self.business.settings(), "titles": titles[:500]}

        # ---------- отзывы ----------
        @self.route("GET", "/api/reviews")
        def reviews_list(user, m, q, body):
            return self.reviews.list(q.get("filter") or "", q.get("q") or "")

        @self.route("POST", "/api/reviews/reply")
        def reviews_reply(user, m, q, body):
            try:
                if body.get("delete"):
                    item = self.reviews.delete_reply(str(body.get("order_id") or ""))
                else:
                    item = self.reviews.reply(str(body.get("order_id") or ""), str(body.get("text") or ""))
            except ReviewError as e:
                raise ApiError(str(e))
            return {"item": item}

        @self.route("POST", "/api/reviews/fetch")
        def reviews_fetch(user, m, q, body):
            try:
                orders = self._load_orders()
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError("Не удалось загрузить заказы с FunPay.", 424)
            return {"job": self.reviews.start_fetch(orders, body.get("limit") or 40)}

        # ---------- покупатели, план, себестоимость ----------
        @self.route("GET", "/api/buyers")
        def buyers(user, m, q, body):
            r = self.sales.request(365, refresh=q.get("refresh") == "1")
            if not r["ready"]:
                if r.get("error"):
                    raise ApiError(r["error"])
                return {"ready": False, "pages": r.get("pages", 0)}
            return {"ready": True, "partial": r["partial"], "covered_from": r["covered_from"],
                    "buyers": self.business.buyers(r["orders"], self.reviews.by_buyer(), crd.blacklist)}

        @self.route("GET", "/api/plan")
        def plan(user, m, q, body):
            r = self.sales.request(max(1, datetime.date.today().day))
            if not r["ready"]:
                if r.get("error"):
                    raise ApiError(r["error"])
                return {"ready": False, "pages": r.get("pages", 0)}
            return {"ready": True, **self.business.plan_status(r["orders"])}

        @self.route("POST", "/api/plan")
        def plan_set(user, m, q, body):
            try:
                return self.business.set_plan(body.get("amount"))
            except ValueError as e:
                raise ApiError(str(e))

        @self.route("GET", "/api/costs")
        def costs(user, m, q, body):
            return self.business.settings()

        @self.route("POST", "/api/costs")
        def costs_set(user, m, q, body):
            try:
                if "default_pct" in body:
                    return self.business.set_default_pct(body.get("default_pct"))
                return self.business.set_cost(str(body.get("title") or ""), body.get("cost"))
            except ValueError as e:
                raise ApiError(str(e))

        # ---------- уведомления и сторож ----------
        @self.route("GET", "/api/notifications")
        def notifications(user, m, q, body):
            return {**self.guard.notification_chats(user["id"]), "guard": self.guard.status()}

        @self.route("POST", "/api/notifications")
        def notifications_set(user, m, q, body):
            try:
                value = self.guard.set_notification(str(body.get("chat") or ""), str(body.get("type") or ""),
                                                    bool(body.get("value")))
            except ValueError as e:
                raise ApiError(str(e))
            return {"ok": True, "value": value}

        @self.route("GET", "/api/guard")
        def guard_status(user, m, q, body):
            return self.guard.status()

        # ---------- резервная копия и журнал ----------
        def backup_blob(body) -> bytes:
            raw = str(body.get("content") or "")
            if "," in raw[:100]:
                raw = raw.split(",", 1)[1]
            try:
                return base64.b64decode(raw, validate=True)
            except (ValueError, TypeError):
                raise ApiError("Файл повреждён — выберите его ещё раз.")

        @self.route("POST", "/api/backup/make")
        def backup_make(user, m, q, body):
            try:
                blob, info = backup_mod.make(str(body.get("password") or ""))
            except backup_mod.BackupError as e:
                raise ApiError(str(e))
            name = f"cardinal-plus-{datetime.date.today().isoformat()}.cpbak"
            logger.info(f"Mini App: {user['id']} создал резервную копию ({info['files']} файлов)")
            if body.get("send"):
                tg = crd.telegram
                import io as _io
                doc = _io.BytesIO(blob)
                doc.name = name
                try:
                    tg.bot.send_document(user["id"], doc, caption=f"🗄 Резервная копия Cardinal+: {info['files']} файлов. "
                                                                  f"Зашифрована вашим паролем. Не пересылайте её.")
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
                    raise ApiError("Не удалось отправить файл в Telegram. Если копия больше 50 МБ — скачайте её.")
                return {"sent": True, **info}
            if len(blob) > 60 * 1024 * 1024:
                raise ApiError("Копия получилась слишком большой для скачивания — отправьте её в Telegram.")
            return {"name": name, "content": base64.b64encode(blob).decode(), **info}

        @self.route("POST", "/api/backup/inspect")
        def backup_inspect(user, m, q, body):
            try:
                return backup_mod.inspect(backup_blob(body), str(body.get("password") or ""))
            except backup_mod.BackupError as e:
                raise ApiError(str(e))

        @self.route("POST", "/api/backup/restore")
        def backup_restore(user, m, q, body):
            from webapp import plugin_installer
            try:
                result = backup_mod.restore(backup_blob(body), str(body.get("password") or ""))
            except backup_mod.BackupError as e:
                raise ApiError(str(e))
            logger.info(f"Mini App: {user['id']} восстановил Cardinal из резервной копии — перезапуск.")
            # файлы уже на месте; перезапуск, чтобы Cardinal прочитал их заново (после ответа приложению)
            plugin_installer.restart(2.0)
            return {"ok": True, **result, "restart": True}

        @self.route("GET", "/api/audit")
        def audit_list(user, m, q, body):
            try:
                limit = max(1, min(1000, int(q.get("limit") or 300)))
            except ValueError:
                limit = 300
            return self.audit.read(q.get("kind") or "", q.get("q") or "", limit)

        @self.route("GET", "/api/plugins")
        def plugins(user, m, q, body):
            items = [self._plugin_entry(u, p) for u, p in crd.plugins.items()]
            items.sort(key=lambda x: (not x["pinned"], not x["has_ui"], x["name"].lower()))
            return {"plugins": items}

        @self.route("POST", "/api/plugins/inspect")
        def plugin_inspect(user, m, q, body):
            from webapp import plugin_installer
            try:
                return plugin_installer.inspect(crd, str(body.get("filename") or ""), body.get("source"), body.get("expect_uuid"))
            except plugin_installer.InstallError as e:
                raise ApiError(str(e), 400)

        @self.route("POST", "/api/plugins/install")
        def plugin_install(user, m, q, body):
            from webapp import plugin_installer
            try:
                result = plugin_installer.install(crd, str(body.get("filename") or ""), body.get("source"), body.get("expect_uuid"))
            except plugin_installer.InstallError as e:
                raise ApiError(str(e), 400)
            logger.info(f"Mini App: {user['id']} {'обновил' if result['update'] else 'установил'} плагин {result['name']}")
            if result["loaded"]:
                result["plugin"] = self._plugin_entry(result["uuid"], crd.plugins[result["uuid"]])
            return result

        @self.route("GET", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/backups")
        def plugin_backups(user, m, q, body):
            from webapp import plugin_installer
            self._get_plugin(m["uuid"])
            return {"backups": plugin_installer.backups(crd, m["uuid"])}

        @self.route("POST", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/rollback")
        def plugin_rollback(user, m, q, body):
            from webapp import plugin_installer
            self._get_plugin(m["uuid"])
            try:
                result = plugin_installer.rollback(crd, m["uuid"], str(body.get("file") or ""))
            except plugin_installer.InstallError as e:
                raise ApiError(str(e), 400)
            logger.info(f"Mini App: {user['id']} вернул прошлую версию плагина {result['name']} (v{result['version']})")
            return result

        @self.route("POST", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/delete")
        def plugin_delete(user, m, q, body):
            from webapp import plugin_installer
            try:
                result = plugin_installer.delete(crd, m["uuid"])
            except plugin_installer.InstallError as e:
                raise ApiError(str(e), 404)
            logger.info(f"Mini App: {user['id']} удалил плагин {result['name']}")
            return {"ok": True, **result}

        @self.route("POST", "/api/restart")
        def restart_cardinal(user, m, q, body):
            from webapp import plugin_installer
            logger.info(f"Mini App: {user['id']} перезапускает Cardinal.")
            plugin_installer.restart()
            return {"ok": True}

        @self.route("POST", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/toggle")
        def toggle_plugin(user, m, q, body):
            uuid = m["uuid"]
            p = self._get_plugin(uuid)
            if bool(body.get("enabled", not p.enabled)) != p.enabled:
                crd.toggle_plugin(uuid)
                logger.info(f"Mini App: {user['id']} {'включил' if p.enabled else 'выключил'} плагин {p.name}")
            return {"ok": True, "enabled": p.enabled}

        @self.route("GET", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})")
        def plugin_detail(user, m, q, body):
            uuid = m["uuid"]
            p = self._get_plugin(uuid)
            spec = plugin_api.get_webapp_spec(p.plugin) or {}
            schema = spec.get("settings") or []
            values = plugin_api.bind_schema(uuid, schema).all() if schema else {}
            if schema and callable(spec.get("values")):  # плагин хранит настройки в своём конфиге
                try:
                    values = {**values, **(spec["values"](crd) or {})}
                except Exception:
                    logger.error(f"Mini App: ошибка в WEBAPP['values'] плагина {p.name}")
                    logger.debug("TRACEBACK", exc_info=True)
            return {
                **self._plugin_entry(uuid, p),
                "settings": plugin_api.public_schema(schema),
                "values": values,
                "page_url": f"/plugin/{uuid}/page" if plugin_api.has_page(spec) else None,
                "page_title": str(spec.get("page_title") or "Страница плагина"),
                "page_first": bool(spec.get("page_first")),
            }

        @self.route("POST", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/settings")
        def plugin_set(user, m, q, body):
            uuid = m["uuid"]
            p = self._get_plugin(uuid)
            spec = plugin_api.get_webapp_spec(p.plugin) or {}
            schema = spec.get("settings") or []
            key = body.get("key")
            field = next((f for f in schema if f.get("key") == key and f.get("type") != "section"), None)
            if field is None:
                raise ApiError("Неизвестная настройка.")
            try:
                value = plugin_api.coerce_value(field, body.get("value"))
            except ValueError as e:
                raise ApiError(str(e))
            if callable(spec.get("save")):  # плагин сам сохраняет значение в свой конфиг
                try:
                    spec["save"](crd, key, value)
                except ValueError as e:
                    raise ApiError(str(e))
            else:
                plugin_api.bind_schema(uuid, schema).set(key, value)
            on_change = spec.get("on_change")
            if callable(on_change):
                try:
                    on_change(crd, key, value)
                except Exception:
                    logger.error(f"Mini App: ошибка в on_change плагина {p.name}")
                    logger.debug("TRACEBACK", exc_info=True)
            return {"ok": True, "value": value}

        @self.route("POST", r"/api/plugins/(?P<uuid>[0-9a-fA-F-]{36})/call/(?P<name>[A-Za-z0-9_\-]+)")
        def plugin_call(user, m, q, body):
            p = self._get_plugin(m["uuid"])
            if not p.enabled:
                raise ApiError("Плагин выключен.", 409)
            spec = plugin_api.get_webapp_spec(p.plugin) or {}
            func = plugin_api.get_route(spec, m["name"])
            if func is None:
                raise ApiError("Метод плагина не найден.", 404)
            try:
                result = func(crd, body)
            except ApiError:
                raise
            except ValueError as e:  # понятная ошибка для пользователя (неверный ввод и т.п.)
                raise ApiError(str(e), 400)
            except Exception as e:
                logger.error(f"Mini App: ошибка в методе {m['name']} плагина {p.name}")
                logger.debug("TRACEBACK", exc_info=True)
                raise ApiError(f"Ошибка плагина: {e}", 500)
            return {"ok": True, "result": result}


class _Handler(BaseHTTPRequestHandler):
    webapp: WebApp
    server_version = "CardinalPlus"
    sys_version = ""

    def log_message(self, fmt, *args):
        logger.debug("Mini App HTTP: " + fmt % args)

    # ---------- ответы ----------
    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            # Встраивать страницу можно только самому приложению и веб-версии Telegram (защита от кликджекинга).
            self.send_header("Content-Security-Policy",
                             "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _file(self, path: str, cache: bool = True):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self._json(404, {"error": "Не найдено"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype, {"Cache-Control": "no-cache" if not cache else "public, max-age=60"})

    # ---------- обработка ----------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self._api(method, path, parsed.query)
        if method not in ("GET", "HEAD"):
            return self._json(405, {"error": "Метод не поддерживается"})

        if path == "/login":
            return self._login(parsed.query)

        m = re.match(r"^/plugin/([0-9a-fA-F-]{36})/page$", path)
        if m:
            return self._plugin_page(m.group(1))

        if path in ("/", "/index.html"):
            return self._file(os.path.join(STATIC_DIR, "index.html"), cache=False)
        if path.startswith("/static/"):
            rel = os.path.normpath(path[len("/static/"):]).replace("\\", "/")
            if rel.startswith("..") or os.path.isabs(rel):
                return self._json(404, {"error": "Не найдено"})
            return self._file(os.path.join(STATIC_DIR, rel), cache=False)
        return self._json(404, {"error": "Не найдено"})

    def _plugin_page(self, uuid: str):
        p = self.webapp.cardinal.plugins.get(uuid)
        spec = plugin_api.get_webapp_spec(p.plugin) if p else None
        if not spec or not plugin_api.has_page(spec):
            return self._json(404, {"error": "У плагина нет страницы"})
        if isinstance(spec.get("page_html"), str):  # страница встроена прямо в .py плагина
            return self._send(200, spec["page_html"].encode("utf-8"), "text/html; charset=utf-8",
                              {"Cache-Control": "no-cache"})
        plugins_dir = os.path.realpath("plugins")
        page = os.path.realpath(os.path.join(os.path.dirname(p.path), spec["page"]))
        if not page.startswith(plugins_dir + os.sep):
            return self._json(403, {"error": "Страница плагина должна лежать в папке plugins"})
        self._file(page, cache=False)

    def _is_https(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https" or '"https"' in self.headers.get("Cf-Visitor", "")

    def _session_cookie(self, value: str, max_age: int) -> str:
        cookie = f"{sessions.COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
        return cookie + ("; Secure" if self._is_https() else "")

    def _login(self, query: str):
        token = (parse_qs(query).get("t") or [""])[0]
        result = sessions.redeem_login_token(token)
        tg = self.webapp.cardinal.telegram
        if result is None or tg is None or result[1] not in tg.authorized_users:
            html = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<title>Cardinal+</title><body style=\"font-family:system-ui,sans-serif;background:#0b0c10;color:#f3f4f6;"
                    "display:grid;place-items:center;height:100vh;margin:0;text-align:center\"><div>"
                    "<div style=\"font-size:22px;font-weight:700;margin-bottom:8px\">Ссылка недействительна</div>"
                    "<div style=\"color:#a7adb8\">Ссылка одноразовая и живёт 5 минут.<br>Отправьте боту <b>/web</b>, "
                    "чтобы получить новую.</div></div></body>")
            return self._send(403, html.encode("utf-8"), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        session, user_id = result
        logger.info(f"Mini App: вход из браузера (Telegram ID {user_id}).")
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", self._session_cookie(session, sessions.SESSION_TTL))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _audit(self, user: dict, path: str, body: dict, result) -> None:
        """Запись в журнал действий (без текстов сообщений и паролей)."""
        try:
            desc = self.webapp.audit.describe(path, body, result)
            if desc:
                self.webapp.audit.add(user, *desc)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)

    def _api(self, method: str, path: str, query: str):
        if path == "/api/logout" and method == "POST":
            sessions.delete_session(read_cookie(self.headers, sessions.COOKIE_NAME))
            body = b'{"ok": true}'
            return self._send(200, body, "application/json; charset=utf-8",
                              {"Set-Cookie": self._session_cookie("", 0), "Cache-Control": "no-store"})
        q = {k: v[0] for k, v in parse_qs(query).items()}
        q["_host"] = self.headers.get("Host", "")
        body: dict = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length > (MAX_BACKUP_BODY if path in BACKUP_ROUTES else MAX_BODY):
                return self._json(413, {"error": "Слишком большой запрос"})
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"error": "Некорректный JSON"})
                if not isinstance(body, dict):
                    return self._json(400, {"error": "Ожидается объект JSON"})

        for r_method, pattern, func in self.webapp.routes:
            match = pattern.match(path)
            if not match or r_method != method:
                continue
            try:
                user = self.webapp.authorize(self.headers)
                result = func(user, match.groupdict(), q, body)
                if method == "POST":
                    self._audit(user, path, body, result)
                return self._json(200, result)
            except ApiError as e:
                return self._json(e.status, {"error": str(e)})
            except Exception:
                logger.error(f"Mini App: ошибка при обработке {method} {path}")
                logger.debug(traceback.format_exc())
                return self._json(500, {"error": "Внутренняя ошибка Cardinal"})
        return self._json(404, {"error": "Метод API не найден"})
