"""
Автоматический HTTPS-туннель через Cloudflare (quick tunnel, без аккаунта и домена).

Cardinal сам открывает исходящее соединение к Cloudflare, а тот выдаёт публичную ссылку
https://<слова>.trycloudflare.com, которая ведёт на локальный веб-сервер Mini App.
Ссылка меняется при каждом перезапуске — поэтому при её получении вызывается on_url,
и Cardinal обновляет кнопку приложения в боте.
"""
from __future__ import annotations

import atexit
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
from typing import Callable

import requests

from webapp import procguard

logger = logging.getLogger("FPC.webapp")

BIN_DIR = os.path.join("storage", "bin")
RELEASE_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _asset_name() -> tuple[str, str]:
    """Имя файла в релизах cloudflared и имя локального бинарника."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine.startswith("arm"):
        arch = "arm"
    elif machine in ("i386", "i686", "x86"):
        arch = "386"
    else:
        arch = "amd64"

    if system == "windows":
        return f"cloudflared-windows-{'386' if arch == '386' else 'amd64'}.exe", "cloudflared.exe"
    if system == "darwin":
        return f"cloudflared-darwin-{'arm64' if arch == 'arm64' else 'amd64'}.tgz", "cloudflared"
    return f"cloudflared-linux-{arch}", "cloudflared"


def find_or_download() -> str:
    """Возвращает путь к cloudflared: системный, ранее скачанный или скачивает с GitHub Cloudflare."""
    system_bin = shutil.which("cloudflared")
    if system_bin:
        return system_bin

    asset, local_name = _asset_name()
    local_path = os.path.join(BIN_DIR, local_name)
    if os.path.exists(local_path):
        return local_path

    os.makedirs(BIN_DIR, exist_ok=True)
    url = RELEASE_URL + asset
    logger.info(f"Mini App: скачиваю cloudflared для туннеля ({asset}), это нужно один раз...")
    tmp_path = os.path.join(BIN_DIR, asset + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

    if asset.endswith(".tgz"):
        with tarfile.open(tmp_path, "r:gz") as tar:
            member = next(m for m in tar.getmembers() if os.path.basename(m.name) == "cloudflared")
            with tar.extractfile(member) as src, open(local_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        os.remove(tmp_path)
    else:
        os.replace(tmp_path, local_path)

    if os.name != "nt":
        os.chmod(local_path, os.stat(local_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logger.info("Mini App: cloudflared скачан.")
    return local_path


class CloudflareTunnel:
    def __init__(self, local_port: int, on_url: Callable[[str], None]):
        self.local_port = local_port
        self.on_url = on_url
        self.url: str | None = None
        self.process: subprocess.Popen | None = None
        self._stopped = False
        atexit.register(self.stop)

    def start(self):
        threading.Thread(target=self._supervise, daemon=True, name="webapp-tunnel").start()

    def stop(self):
        self._stopped = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _supervise(self):
        procguard.kill_orphans(f"http://127.0.0.1:{self.local_port}")  # туннели, брошенные прошлыми запусками
        delay = 5
        while not self._stopped:
            try:
                binary = find_or_download()
            except Exception:
                logger.error("Mini App: не удалось скачать cloudflared. Повторю через минуту.")
                logger.debug("TRACEBACK", exc_info=True)
                time.sleep(60)
                continue

            started = time.time()
            try:
                self._run_once(binary)
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
            if self._stopped:
                return
            # Если туннель проработал долго — перезапускаем быстро, иначе увеличиваем паузу.
            delay = 5 if time.time() - started > 300 else min(delay * 2, 300)
            logger.warning(f"Mini App: туннель остановился, перезапуск через {delay} сек.")
            time.sleep(delay)

    def _run_once(self, binary: str):
        cmd = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.local_port}"]
        kwargs = procguard.popen_kwargs()
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                        stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        errors="replace", bufsize=1, **kwargs)
        procguard.bind_to_parent(self.process)  # закроется вместе с Cardinal, даже если окно закрыли крестиком
        logger.info("Mini App: запускаю туннель Cloudflare...")
        pending_url = None
        for line in self.process.stderr:
            logger.debug(f"cloudflared: {line.rstrip()}")
            m = URL_RE.search(line)
            if m:
                pending_url = m.group(0)
            # Адрес отдаём дальше только когда туннель реально подключился к Cloudflare.
            if pending_url and pending_url != self.url and "Registered tunnel connection" in line:
                self.url = pending_url
                logger.info(f"Mini App: туннель подключён, адрес {self.url}")
                try:
                    self.on_url(self.url)
                except Exception:
                    logger.error("Mini App: не удалось применить новый адрес.")
                    logger.debug("TRACEBACK", exc_info=True)
        self.process.wait()
        self.url = None
