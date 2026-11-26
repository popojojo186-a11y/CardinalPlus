"""
Cardinal Plus — Telegram Mini App для FunPay Cardinal.

Точка входа: webapp.start(cardinal) — вызывается из Cardinal.init() после запуска Telegram-бота.
"""
from __future__ import annotations

import logging
import os
import secrets
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import requests
from urllib.parse import urlparse

from webapp import config as webapp_config

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

_state: dict = {"app": None, "tunnel": None, "url": None, "front": None}


def get_public_url() -> str | None:
    return _state["url"]


def start(cardinal: Cardinal) -> None:
    cfg = webapp_config.load()
    if not cfg.get("enabled", True):
        logger.info("Mini App выключен (configs/webapp.json).")
        return
    if cardinal.telegram is None:
        logger.warning("Mini App не запущен: Telegram-бот выключен в настройках Cardinal.")
        return

    from webapp.server import WebApp

    host = cfg.get("host") or "127.0.0.1"
    port = int(cfg.get("port") or 8095)
    public_url = (cfg.get("public_url") or "").strip().rstrip("/")
    tunnel_mode = "none" if public_url or cfg.get("tunnel", "cloudflare") != "cloudflare" else "cloudflare"
    # Входная дверь держит адрес и туннель отдельно от Cardinal — тогда перезапуск Cardinal не ломает приложение.
    use_front = bool(cfg.get("keep_alive", True)) and not getattr(sys, "frozen", False) and host == "127.0.0.1"
    listen = int(cfg.get("backend_port") or port + 100) if use_front else port
    app = None
    for p in range(listen, listen + 10):
        try:
            app = WebApp(cardinal, host, p)
            app.start()
            break
        except OSError:
            logger.warning(f"Mini App: порт {p} занят, пробую следующий.")
            app = None
    if app is None:
        logger.error("Mini App: не удалось запустить веб-сервер — все порты заняты.")
        return
    _state["app"] = app
    _register_bot_command(cardinal)
    from webapp import plus_updater
    plus_updater.start(cardinal)  # проверка новых версий Cardinal Plus на GitHub

    if use_front:
        front = _ensure_front(port, app.port, tunnel_mode, int(cfg.get("keep_alive_idle") or 180))
        if front:
            _state["front"] = front
            if not front["reused"] and not public_url:
                threading.Thread(target=_reset_menu_button, args=(cardinal,), daemon=True).start()
            threading.Thread(target=_front_loop, args=(cardinal, cfg, public_url, tunnel_mode), daemon=True,
                             name="webapp-front").start()
            return
        logger.warning("Mini App: не получилось запустить входную дверь — работаю по-старому "
                       "(при перезапуске Cardinal адрес приложения будет меняться).")

    if not public_url:
        threading.Thread(target=_reset_menu_button, args=(cardinal,), daemon=True).start()
    if public_url:
        threading.Thread(target=_apply_url, args=(cardinal, public_url, cfg), daemon=True).start()
    elif cfg.get("tunnel", "cloudflare") == "cloudflare":
        from webapp.tunnel import CloudflareTunnel
        tunnel = CloudflareTunnel(app.port, lambda url: threading.Thread(
            target=_apply_url, args=(cardinal, url, cfg), daemon=True).start())
        _state["tunnel"] = tunnel
        tunnel.start()
    else:
        logger.warning("Mini App: туннель выключен и public_url не указан — приложение доступно только локально.")


# ───────────── входная дверь (webapp/front.py) ─────────────
def _front_key_path(port: int) -> str:
    return os.path.join("storage", "cache", f"webapp_front_{port}.key")


def _front_hello(port: int, token: str, backend: int, timeout: float = 3):
    """Сказать двери «я жив, я на таком-то порту». Ответ: {"url", "version", "tunnel"} или None."""
    from webapp import front as front_mod
    try:
        r = requests.post(f"http://127.0.0.1:{port}/__front/hello", json={"backend": backend, "version": front_mod.FRONT_VERSION},
                          headers={"X-Front-Token": token}, timeout=timeout, proxies={"http": None, "https": None})
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _ensure_front(port: int, backend: int, tunnel_mode: str, idle: int = 180):
    """Найти уже работающую дверь (тогда адрес приложения прежний) или запустить новую."""
    from webapp import front as front_mod
    token = ""
    try:
        with open(_front_key_path(port), encoding="utf-8") as f:
            token = f.read().strip()
    except OSError:
        pass
    if token:
        r = _front_hello(port, token, backend)
        if r and r.get("version") == front_mod.FRONT_VERSION and r.get("tunnel") == tunnel_mode:
            logger.info("Mini App: входная дверь уже работает — адрес приложения не изменился.")
            return {"port": port, "token": token, "reused": True}
        if r:  # старая версия двери или другой режим туннеля — закрываем и запускаем новую
            try:
                requests.post(f"http://127.0.0.1:{port}/__front/stop", headers={"X-Front-Token": token}, timeout=3,
                              proxies={"http": None, "https": None})
            except requests.RequestException:
                pass
            time.sleep(2)
    token = secrets.token_urlsafe(24)
    os.makedirs(os.path.dirname(_front_key_path(port)), exist_ok=True)
    with open(_front_key_path(port), "w", encoding="utf-8") as f:
        f.write(token)
    cmd = [sys.executable, "-m", "webapp.front", "--port", str(port), "--backend", str(backend), "--tunnel", tunnel_mode,
           "--idle", str(max(30, idle))]
    kw = {"cwd": os.getcwd(), "env": {**os.environ, "CP_FRONT_TOKEN": token}, "stdin": subprocess.DEVNULL,
          "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    try:
        if os.name == "nt":
            base = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: живёт отдельно от окна Cardinal
            try:
                subprocess.Popen(cmd, creationflags=base | 0x01000000, **kw)   # CREATE_BREAKAWAY_FROM_JOB
            except OSError:
                subprocess.Popen(cmd, creationflags=base, **kw)
        else:
            subprocess.Popen(cmd, start_new_session=True, **kw)
    except OSError:
        logger.debug("TRACEBACK", exc_info=True)
        return None
    for _ in range(40):
        time.sleep(0.25)
        if _front_hello(port, token, backend):
            logger.info(f"Mini App: входная дверь запущена на порту {port} — перезапуски Cardinal больше не меняют адрес приложения.")
            return {"port": port, "token": token, "reused": False}
    return None


def _front_loop(cardinal: Cardinal, cfg: dict, public_url: str, tunnel_mode: str) -> None:
    """Раз в 15 секунд говорим двери, что Cardinal жив, и узнаём адрес туннеля (он меняется только если дверь перезапустилась)."""
    if public_url:
        _apply_url(cardinal, public_url, cfg)
    fails = 0
    while True:
        front, app = _state["front"], _state["app"]
        r = _front_hello(front["port"], front["token"], app.port) if front and app else None
        if r is None:
            fails += 1
            if fails >= 3:   # дверь закрыли или она упала — поднимаем новую
                new = _ensure_front(front["port"], app.port, tunnel_mode, int(cfg.get("keep_alive_idle") or 180))
                if new:
                    _state["front"] = new
                    fails = 0
        else:
            fails = 0
            url = r.get("url")
            if not public_url and url and url != _state["url"]:
                _apply_url(cardinal, url, cfg)
        time.sleep(2 if not public_url and not _state["url"] else 15)


DOH_SERVERS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")


def _wait_dns(url: str, timeout: int = 120) -> bool:
    """
    Ждёт, пока домен туннеля появится в DNS. Проверяем через DNS-over-HTTPS (Cloudflare/Google),
    а НЕ через системный DNS: если роутер или провайдер спросит домен слишком рано, он запомнит
    ответ «домена нет» на несколько минут, и приложение не откроется.
    """
    host = urlparse(url).hostname
    deadline = time.time() + timeout
    doh_failed = 0
    while time.time() < deadline:
        for server in DOH_SERVERS:
            try:
                r = requests.get(server, params={"name": host, "type": "A"},
                                 headers={"accept": "application/dns-json"}, timeout=8)
                data = r.json()
                if data.get("Status") == 0 and any(a.get("type") == 1 for a in data.get("Answer") or []):
                    return True
                break
            except (requests.RequestException, ValueError):
                doh_failed += 1
                continue
        if doh_failed >= 6:
            # DoH недоступен — просто ждём с запасом, не трогая системный DNS.
            logger.debug("Mini App: DNS-over-HTTPS недоступен, жду 25 секунд.")
            time.sleep(25)
            return False
        time.sleep(2)
    return False


def _wait_reachable(url: str, timeout: int = 150) -> bool:
    """Новый адрес trycloudflare начинает открываться не сразу — ждём, пока DNS разойдётся."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url + "/static/app.js", timeout=10)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False


def _apply_url(cardinal: Cardinal, url: str, cfg: dict) -> None:
    # Кнопку ставим только когда домен уже есть в DNS, иначе Telegram откроет его слишком рано
    # и роутер закэширует «домен не найден».
    if url.endswith(".trycloudflare.com"):
        logger.info("Mini App: жду, пока адрес появится в DNS (обычно 5–20 секунд)...")
        _wait_dns(url)
        time.sleep(3)  # небольшой запас, чтобы запись успела разойтись
    _state["url"] = url
    if _state["app"]:
        _state["app"].public_url = url
    _set_menu_button(cardinal, url, cfg.get("menu_button_text") or "Cardinal+")
    if _wait_reachable(url):
        logger.info("Mini App: приложение готово — нажмите кнопку «%s» в боте." % (cfg.get("menu_button_text") or "Cardinal+"))
    else:
        logger.warning("Mini App: адрес туннеля пока не отвечает, приложение может открыться не сразу.")


def _reset_menu_button(cardinal: Cardinal) -> None:
    """Пока туннель не готов, убираем кнопку со старым (уже мёртвым) адресом прошлого запуска."""
    from telebot.types import MenuButtonCommands
    bot = cardinal.telegram.bot
    try:
        bot.set_chat_menu_button(menu_button=MenuButtonCommands("commands"))
        for user_id in list(cardinal.telegram.authorized_users):
            if _state["url"]:
                return
            bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonCommands("commands"))
    except Exception:
        logger.debug("TRACEBACK", exc_info=True)


def _set_menu_button(cardinal: Cardinal, url: str, text: str) -> None:
    from telebot.types import MenuButtonWebApp, WebAppInfo
    bot = cardinal.telegram.bot
    button = MenuButtonWebApp("web_app", text, WebAppInfo(url))
    # Кнопка для всех чатов по умолчанию + явно для каждого авторизованного пользователя.
    bot.set_chat_menu_button(menu_button=button)
    for user_id in list(cardinal.telegram.authorized_users):
        try:
            bot.set_chat_menu_button(chat_id=user_id, menu_button=button)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
    logger.info("Mini App: кнопка приложения в боте обновлена.")


def _register_bot_command(cardinal: Cardinal) -> None:
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Message
    tg = cardinal.telegram

    def send_app(m: Message):
        if m.from_user.id not in tg.authorized_users:
            return
        url = _state["url"]
        if not url:
            tg.bot.send_message(m.chat.id, "⏳ Приложение ещё запускается, попробуйте через несколько секунд.")
            return
        if m.chat.type != "private":
            tg.bot.send_message(m.chat.id, "Приложение открывается только в личном чате с ботом.")
            return
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📱 Открыть Cardinal+", web_app=WebAppInfo(url)))
        tg.bot.send_message(m.chat.id, "Панель управления Cardinal:", reply_markup=kb)

    def send_web_link(m: Message):
        if m.from_user.id not in tg.authorized_users:
            return
        if m.chat.type != "private":
            tg.bot.send_message(m.chat.id, "Ссылку для входа можно получить только в личном чате с ботом.")
            return
        app = _state["app"]
        if not app or not _state["url"]:
            tg.bot.send_message(m.chat.id, "⏳ Приложение ещё запускается, попробуйте через несколько секунд.")
            return
        link = app.login_link(m.from_user.id)
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🖥 Открыть в браузере", url=link))
        tg.bot.send_message(m.chat.id, "Вход в Панель Cardinal+ из браузера.\n\n"
                                       "Ссылка одноразовая и действует 5 минут. Никому её не пересылайте.",
                            reply_markup=kb)

    tg.msg_handler(send_app, commands=["app"])
    tg.msg_handler(send_web_link, commands=["web"])
    tg.add_command_to_menu("app", "📱 Открыть приложение")
    tg.add_command_to_menu("web", "🖥 Открыть Панель в браузере")
