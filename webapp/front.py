"""
«Входная дверь» Cardinal Plus — маленький отдельный процесс, который держит адрес приложения и туннель Cloudflare.

Cardinal работает за ней на внутреннем порту. Когда Cardinal перезапускается (кнопка «Перезапустить», /restart,
установка плагина, обновление), дверь остаётся: адрес приложения не меняется, туннель не пересоздаётся,
а пока Cardinal поднимается, приложение показывает «Cardinal перезапускается…» и потом само подключается.

Если Cardinal не отзывается дольше --idle секунд (окно закрыли), дверь закрывается сама вместе с туннелем.

Запуск (это делает сам Cardinal): python -m webapp.front --port 8095 --backend 8195 [--tunnel cloudflare|none]
Секретный ключ для служебных запросов передаётся в переменной окружения CP_FRONT_TOKEN.
"""
from __future__ import annotations

import argparse
import hmac
import http.client
import json
import logging
import logging.handlers
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

FRONT_VERSION = 1
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 64 * 1024 * 1024
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding",
       "upgrade", "content-length"}
RESTARTING = {"error": "Cardinal перезапускается — подождите несколько секунд, приложение подключится само.",
              "restarting": True}
WAIT_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3"><title>Cardinal+</title><style>body{font:16px system-ui,sans-serif;display:grid;place-items:center;
min-height:90vh;margin:0;background:#111;color:#eee;text-align:center}p{opacity:.7}</style></head><body><div><h2>Cardinal перезапускается…</h2>
<p>Страница обновится сама через пару секунд.</p></div></body></html>"""

logger = logging.getLogger("FPC.webapp.front")


def state_path(port: int) -> str:
    return os.path.join("storage", "cache", f"webapp_front_{port}.json")


class Front:
    def __init__(self, port: int, backend: int, token: str, tunnel: str, idle: int):
        self.port, self.backend, self.token, self.tunnel_mode, self.idle = port, backend, token, tunnel, idle
        self.last_seen = time.time()
        self.url: str | None = None
        self.tunnel = None
        self.httpd: ThreadingHTTPServer | None = None
        self.stopping = threading.Event()

    # ---------- жизнь процесса ----------
    def run(self) -> None:
        front = self

        class Handler(_Handler):
            app = front

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.httpd.daemon_threads = True
        self._write_state()
        if self.tunnel_mode == "cloudflare":
            from webapp.tunnel import CloudflareTunnel
            self.tunnel = CloudflareTunnel(self.port, self._on_url)
            self.tunnel.start()
        threading.Thread(target=self._watch_idle, daemon=True, name="front-idle").start()
        logger.info(f"Входная дверь Cardinal Plus запущена на 127.0.0.1:{self.port}, Cardinal — на порту {self.backend}.")
        try:
            self.httpd.serve_forever(poll_interval=0.5)
        finally:
            self._cleanup()

    def _on_url(self, url: str) -> None:
        self.url = url
        logger.info(f"Туннель подключён: {url}")

    def _watch_idle(self) -> None:
        while not self.stopping.wait(2):
            if time.time() - self.last_seen > self.idle:
                logger.info(f"Cardinal не отзывается {self.idle} сек. — закрываю дверь и туннель.")
                self.stop()

    def stop(self) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        if self.tunnel:
            try:
                self.tunnel.stop()
            except Exception:
                pass
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    def _write_state(self) -> None:
        os.makedirs(os.path.dirname(state_path(self.port)), exist_ok=True)
        with open(state_path(self.port), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "port": self.port, "backend": self.backend, "version": FRONT_VERSION,
                       "started": int(time.time())}, f)

    def _cleanup(self) -> None:
        try:
            with open(state_path(self.port), encoding="utf-8") as f:
                mine = json.load(f).get("pid") == os.getpid()
            if mine:
                os.remove(state_path(self.port))
        except (OSError, ValueError):
            pass


class _Handler(BaseHTTPRequestHandler):
    app: Front
    server_version = "CardinalPlus"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.debug("front: " + fmt % args)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()

    # ---------- ответы ----------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too big")
        return self.rfile.read(n) if n > 0 else b""

    # ---------- служебные запросы Cardinal ----------
    def _control(self, path: str) -> None:
        # снаружи (через туннель Cloudflare) служебные адреса не существуют
        token = self.headers.get("X-Front-Token") or ""
        if self.headers.get("Cf-Ray") or self.headers.get("Cf-Connecting-Ip") or \
                not hmac.compare_digest(token.encode(), self.app.token.encode()):
            return self._json(404, {"error": "Не найдено"})
        body = self._read_body()
        if path == "/__front/hello":
            try:
                data = json.loads(body or b"{}")
            except ValueError:
                data = {}
            if isinstance(data.get("backend"), int):
                self.app.backend = data["backend"]
            self.app.last_seen = time.time()
            return self._json(200, {"url": self.app.url, "version": FRONT_VERSION, "pid": os.getpid(),
                                    "tunnel": self.app.tunnel_mode})
        if path == "/__front/stop":
            self._json(200, {"ok": True})
            return self.app.stop()
        return self._json(404, {"error": "Не найдено"})

    # ---------- пересылка в Cardinal ----------
    def _handle(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/__front/"):
            return self._control(path)
        try:
            body = self._read_body()
        except ValueError:
            return self._json(413, {"error": "Слишком большой запрос"})
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        conn = http.client.HTTPConnection("127.0.0.1", self.app.backend, timeout=180)
        try:
            conn.connect()
        except OSError:
            conn.close()
            return self._backend_down(path)                  # Cardinal ещё не поднялся — запрос туда не ушёл
        try:
            conn.request(self.command, self.path, body=body or None, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except (OSError, http.client.HTTPException):
            conn.close()
            if self.command in ("GET", "HEAD"):
                return self._backend_down(path)
            # запрос ушёл, а ответа нет — повторять нельзя (действие могло выполниться)
            return self._json(424, {"error": "Связь с Cardinal прервалась — проверьте, выполнилось ли действие."})
        conn.close()
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _backend_down(self, path: str) -> None:
        if path.startswith("/api/"):
            return self._json(425, RESTARTING)              # 425 «рано»: приложение подождёт и повторит
        if self.command in ("GET", "HEAD") and (path in ("/", "/index.html") or path.startswith("/static/")):
            rel = "index.html" if path in ("/", "/index.html") else os.path.normpath(path[len("/static/"):]).replace("\\", "/")
            full = os.path.join(STATIC_DIR, rel)
            if not rel.startswith("..") and not os.path.isabs(rel) and os.path.isfile(full):
                with open(full, "rb") as f:
                    data = f.read()
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype == "application/javascript":
                    ctype += "; charset=utf-8"
                return self._send(200, data, ctype)
        return self._send(200, WAIT_PAGE.encode("utf-8"), "text/html; charset=utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--backend", type=int, required=True)
    ap.add_argument("--tunnel", default="cloudflare", choices=("cloudflare", "none"))
    ap.add_argument("--idle", type=int, default=180)
    a = ap.parse_args(argv)
    token = os.environ.get("CP_FRONT_TOKEN") or ""
    if len(token) < 16:
        print("CP_FRONT_TOKEN не задан", file=sys.stderr)
        return 2
    os.makedirs("logs", exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(os.path.join("logs", "webapp_front.log"), maxBytes=512 * 1024,
                                                   backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname).1s: %(message)s", "%d.%m.%y %H:%M:%S"))
    for name in ("FPC.webapp", "FPC.webapp.front"):
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = False
    try:
        Front(a.port, a.backend, token, a.tunnel, a.idle).run()
    except OSError as e:
        logger.error(f"Не удалось запустить входную дверь на порту {a.port}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
