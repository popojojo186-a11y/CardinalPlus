"""
Обновление Cardinal Plus из релизов на GitHub.

- Автор выкладывает сборку («Собрать сборку.bat») в релиз своего репозитория: тег v1.1.0, файл CardinalPlus-1.1.0.zip,
  в описании — что нового. Репозиторий указан в webapp/version.py (UPDATE_REPO).
- Cardinal Plus раз в 6 часов спрашивает GitHub о последнем релизе. Если версия новее — пишет в бот и показывает в приложении.
- По кнопке «Обновить» (приложение → Настройки → Обновление) или команде /update: скачивает архив, проверяет его,
  сохраняет копию текущих файлов (storage/plus_backups), заменяет файлы программы и перезапускает Cardinal.
  Папки configs, storage, logs и plugins не трогаются никогда. Если замена сорвалась — файлы возвращаются из копии.
"""
from __future__ import annotations

import html
import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from urllib.parse import urlparse

import requests

from webapp import version as plus_version

logger = logging.getLogger("FPC.webapp")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # папка Cardinal
API = "https://api.github.com/repos/{repo}/releases/latest"
CHECK_EVERY = 6 * 3600
FIRST_CHECK = 90
MIN_GAP = 600                         # не чаще раза в 10 минут без кнопки «Проверить»
MAX_SIZE = 50 * 1024 * 1024           # архив больше — что-то не то
MAX_UNPACKED = 200 * 1024 * 1024
KEEP_BACKUPS = 3
PROTECTED = {"configs", "storage", "logs", "plugins"}                # данные пользователя — не трогаем
SKIP_TOP = PROTECTED | {"venv", "venv2", ".venv", ".git", ".idea", ".vscode", ".github", "build", "dist"}
REQUIRED = ("main.py", "cardinal.py", "webapp/server.py", "webapp/version.py")
ALLOWED_HOSTS = ("github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
                 "codeload.github.com")
ASSET = re.compile(r"^CardinalPlus.*\.zip$", re.I)
STAGES = {"download": "Скачиваю обновление…", "verify": "Проверяю архив…", "backup": "Сохраняю копию текущей версии…",
          "install": "Заменяю файлы программы…", "libraries": "Ставлю новые библиотеки…", "restart": "Перезапускаю Cardinal…"}


class UpdateError(Exception):
    pass


_lock = threading.Lock()
_install_lock = threading.Lock()
_state: dict = {"checked": 0, "latest": None, "error": None, "busy": False, "stage": "", "result": None}


def _path(*parts) -> str:
    return os.path.join(ROOT, *parts)


STATE_FILE = os.path.join("storage", "cache", "plus_update.json")
BACKUP_DIR = os.path.join("storage", "plus_backups")


# ───────────────────────────── версии ─────────────────────────────────────────
def parse_version(s) -> tuple:
    nums = re.findall(r"\d+", str(s or ""))[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums)) if nums else ()


def newer(a, b) -> bool:
    pa, pb = parse_version(a), parse_version(b)
    return bool(pa) and pa > pb


def repo() -> str:
    return (plus_version.UPDATE_REPO or "").strip().strip("/")


# ───────────────────────────── GitHub ─────────────────────────────────────────
def http_get(url: str, stream: bool = False, timeout: float = 20):
    """Запрос к GitHub (в проверках подменяется выдуманным GitHub)."""
    return requests.get(url, stream=stream, timeout=timeout, allow_redirects=True,
                        headers={"Accept": "application/vnd.github+json", "User-Agent": "CardinalPlus-updater"})


def check(force: bool = False) -> dict:
    """Спросить GitHub о последнем выпуске. Без force — не чаще раза в 10 минут."""
    if not repo():
        return status()
    with _lock:
        recent = not force and time.time() - _state["checked"] < MIN_GAP
        if not recent:
            _state["checked"] = time.time()
    if recent:
        return status()
    try:
        r = http_get(API.format(repo=repo()))
        if r.status_code == 404:
            raise UpdateError("На GitHub пока нет ни одного выпуска Cardinal Plus.")
        if r.status_code == 403:
            raise UpdateError("GitHub временно ограничил запросы — попробуйте через час.")
        if r.status_code != 200:
            raise UpdateError(f"GitHub ответил ошибкой {r.status_code}.")
        data = r.json()
        tag = str(data.get("tag_name") or "")
        asset = next((a for a in data.get("assets") or [] if ASSET.match(str(a.get("name") or ""))), None)
        latest = {"version": tag.lstrip("vV") or "?", "name": str(data.get("name") or tag), "notes": str(data.get("body") or "")[:4000],
                  "page": data.get("html_url"), "published": data.get("published_at"),
                  "url": asset.get("browser_download_url") if asset else None, "size": int(asset.get("size") or 0) if asset else 0}
        with _lock:
            _state["latest"] = latest
            _state["error"] = None if asset or not newer(latest["version"], plus_version.VERSION) else \
                "В новом выпуске на GitHub нет архива CardinalPlus-….zip."
    except UpdateError as e:
        with _lock:
            _state["error"] = str(e)
    except (requests.RequestException, ValueError):
        logger.debug("TRACEBACK", exc_info=True)
        with _lock:
            _state["error"] = "Нет связи с GitHub — попробуйте позже."
    return status()


def status() -> dict:
    with _lock:
        latest = _state["latest"]
        return {"version": plus_version.VERSION, "configured": bool(repo()), "repo": repo(), "checked": int(_state["checked"]),
                "error": _state["error"], "busy": _state["busy"], "stage": _state["stage"],
                "stage_text": STAGES.get(_state["stage"], ""), "result": _state["result"],
                "available": bool(latest and latest.get("url") and newer(latest["version"], plus_version.VERSION)),
                "latest": {k: latest.get(k) for k in ("version", "name", "notes", "size", "page", "published")} if latest else None}


# ───────────────────────────── установка ──────────────────────────────────────
def _stage(name: str) -> None:
    with _lock:
        _state["stage"] = name
    if name in STAGES:
        logger.info(f"Cardinal Plus: {STAGES[name]}")


def _download(url: str, size: int) -> bytes:
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme != "https" or host not in ALLOWED_HOSTS:
        raise UpdateError("Ссылка на архив ведёт не на GitHub — обновление отменено.")
    if size and size > MAX_SIZE:
        raise UpdateError("Архив обновления слишком большой — обновление отменено.")
    try:
        r = http_get(url, stream=True, timeout=60)
        if r.status_code != 200:
            raise UpdateError(f"Не удалось скачать архив: GitHub ответил {r.status_code}.")
        final = (urlparse(getattr(r, "url", url)).hostname or "").lower()
        if final and final not in ALLOWED_HOSTS:
            raise UpdateError("Архив пришёл не с GitHub — обновление отменено.")
        buf = io.BytesIO()
        for chunk in r.iter_content(64 * 1024):
            buf.write(chunk)
            if buf.tell() > MAX_SIZE:
                raise UpdateError("Архив обновления слишком большой — обновление отменено.")
        return buf.getvalue()
    except requests.RequestException:
        raise UpdateError("Не удалось скачать архив — нет связи с GitHub.")


def _members(data: bytes) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]]:
    """Файлы программы из архива: путь внутри Cardinal -> запись архива. Всё подозрительное — отказ."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError("Скачанный файл — не архив. Обновление отменено.")
    names = [i for i in z.infolist() if not i.is_dir()]
    # сборка лежит в одной папке (CardinalPlus/…) — её имя отрезаем; если файлы лежат сразу в корне — берём как есть
    first = {i.filename.replace("\\", "/").split("/")[0] for i in names}
    nested = all("/" in i.filename.replace("\\", "/") for i in names)
    prefix = next(iter(first)) + "/" if names and len(first) == 1 and nested else ""
    out, total = {}, 0
    for i in names:
        name = i.filename.replace("\\", "/")
        if prefix and not name.startswith(prefix):
            raise UpdateError("Странное устройство архива — обновление отменено.")
        rel = name[len(prefix):]
        parts = rel.split("/")
        if not rel or rel.startswith("/") or ":" in rel or any(p in ("", "..") for p in parts):
            raise UpdateError("В архиве опасный путь к файлу — обновление отменено.")
        if parts[0] in PROTECTED:
            raise UpdateError(f"В архиве есть папка {parts[0]} — её обновление трогать не должно. Обновление отменено.")
        if "__pycache__" in parts or rel.endswith((".pyc", ".pyo")):
            continue
        total += i.file_size
        out[rel] = i
    if total > MAX_UNPACKED:
        raise UpdateError("Архив обновления слишком большой — обновление отменено.")
    missing = [r for r in REQUIRED if r not in out]
    if missing:
        raise UpdateError("Это не сборка Cardinal Plus (нет " + ", ".join(missing) + "). Обновление отменено.")
    return z, out


def _archive_version(z: zipfile.ZipFile, members: dict) -> str:
    m = re.search(rb'^VERSION\s*=\s*"([^"]+)"', z.read(members["webapp/version.py"]), re.M)
    return m.group(1).decode() if m else ""


def program_files() -> list[str]:
    """Файлы программы в папке Cardinal (без данных пользователя) — то, что попадает в копию перед обновлением."""
    out = []
    for folder, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(folder, ROOT)
        parts = [] if rel == "." else rel.split(os.sep)
        if parts and (parts[0] in SKIP_TOP or "__pycache__" in parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != "__pycache__" and not (not parts and d in SKIP_TOP)]
        for f in files:
            if f.endswith((".pyc", ".pyo", ".plusnew")):
                continue
            out.append("/".join(parts + [f]))
    return sorted(out)


def _backup() -> str:
    os.makedirs(_path(BACKUP_DIR), exist_ok=True)
    name = f"CardinalPlus-{plus_version.VERSION}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    path = _path(BACKUP_DIR, name)
    with zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED) as z:
        for rel in program_files():
            z.write(_path(*rel.split("/")), rel)
    os.replace(path + ".part", path)
    old = sorted(f for f in os.listdir(_path(BACKUP_DIR)) if f.startswith("CardinalPlus-") and f.endswith(".zip"))
    for f in old[:-KEEP_BACKUPS]:
        try:
            os.remove(_path(BACKUP_DIR, f))
        except OSError:
            pass
    return path


def _write(rel: str, data: bytes) -> None:
    target = _path(*rel.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".plusnew"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, target)


def _apply(z: zipfile.ZipFile, members: dict) -> None:
    for rel, info in members.items():
        _write(rel, z.read(info))


def restore(backup_path: str) -> None:
    """Вернуть файлы программы из копии (её делает обновление перед заменой файлов)."""
    with zipfile.ZipFile(backup_path) as z:
        for info in z.infolist():
            if not info.is_dir():
                _write(info.filename, z.read(info))


def _pip() -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=ROOT, capture_output=True,
                           text=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            logger.warning("Cardinal Plus: не удалось поставить новые библиотеки — запустите Setup.bat.")
            logger.debug(r.stdout[-2000:] + r.stderr[-2000:])
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        logger.debug("TRACEBACK", exc_info=True)
        return False


def _load_saved() -> dict:
    try:
        with open(_path(STATE_FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_path(STATE_FILE)), exist_ok=True)
    with open(_path(STATE_FILE), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def install(restart: bool = True) -> dict:
    """Скачать и поставить новую версию. Возвращает {"from", "to", "backup", "libraries"}; при ошибке — UpdateError."""
    if not _install_lock.acquire(blocking=False):
        raise UpdateError("Обновление уже идёт.")
    try:
        with _lock:
            _state.update(busy=True, result=None)
        st = check(force=True)
        if not st["available"]:
            raise UpdateError(st["error"] or f"У вас последняя версия Cardinal Plus {plus_version.VERSION}.")
        latest = _state["latest"]
        _stage("download")
        data = _download(latest["url"], latest["size"])
        _stage("verify")
        z, members = _members(data)
        new_version = _archive_version(z, members)
        if not newer(new_version, plus_version.VERSION):
            raise UpdateError(f"В архиве версия {new_version or '?'}, а у вас уже {plus_version.VERSION}. Обновление отменено.")
        old_req = b""
        if os.path.exists(_path("requirements.txt")):
            with open(_path("requirements.txt"), "rb") as f:
                old_req = f.read()
        _stage("backup")
        backup = _backup()
        _stage("install")
        try:
            _apply(z, members)
        except Exception:
            logger.error("Cardinal Plus: не удалось заменить файлы — возвращаю прежнюю версию.")
            logger.debug("TRACEBACK", exc_info=True)
            restore(backup)
            raise UpdateError("Не получилось заменить файлы программы — всё вернул как было. Возможно, файлы заняты другой программой.")
        libraries = True
        if "requirements.txt" in members and z.read(members["requirements.txt"]) != old_req:
            _stage("libraries")
            libraries = _pip()
        saved = _load_saved()
        saved.update(installed=new_version, previous=plus_version.VERSION, at=int(time.time()), announced=False, backup=backup)
        _save(saved)
        result = {"from": plus_version.VERSION, "to": new_version, "backup": os.path.relpath(backup, ROOT), "libraries": libraries}
        logger.info(f"Cardinal Plus: обновление {plus_version.VERSION} → {new_version} установлено.")
        with _lock:
            _state["result"] = result
        if restart:
            _stage("restart")
            from webapp import plugin_installer
            plugin_installer.restart(delay=2)
        return result
    finally:
        with _lock:
            _state["busy"] = False
            if _state["stage"] != "restart":
                _state["stage"] = ""
        _install_lock.release()


def install_async() -> None:
    def run():
        try:
            install()
        except UpdateError as e:
            with _lock:
                _state["error"] = str(e)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            with _lock:
                _state["error"] = "Обновление не удалось — работает прежняя версия."
    with _lock:
        if _state["busy"]:
            raise UpdateError("Обновление уже идёт.")
        _state.update(busy=True, error=None, stage="download")
    threading.Thread(target=run, daemon=True, name="plus-update-install").start()


# ───────────────────────────── Telegram ───────────────────────────────────────
def _notes(text: str, limit: int = 1500) -> str:
    text = (text or "").strip()
    return html.escape(text[:limit] + ("…" if len(text) > limit else ""))


def _broadcast(cardinal, text: str) -> None:
    tg = getattr(cardinal, "telegram", None)
    if not tg:
        return
    for uid in list(tg.authorized_users):
        try:
            tg.bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)


def notify_if_new(cardinal) -> bool:
    """Сообщить в бот о новой версии (один раз на версию)."""
    st = status()
    if not st["available"]:
        return False
    v = st["latest"]["version"]
    saved = _load_saved()
    if saved.get("notified") == v:
        return False
    notes = _notes(st["latest"]["notes"])
    _broadcast(cardinal, f"🆕 <b>Вышла Cardinal Plus {html.escape(v)}</b> (у вас {plus_version.VERSION})"
                         + (f"\n\n{notes}" if notes else "")
                         + "\n\nОбновить: приложение → Настройки → «Обновление» или команда /update. "
                           "Настройки и плагины сохранятся.")
    saved["notified"] = v
    _save(saved)
    return True


def announce_installed(cardinal) -> bool:
    """После перезапуска: «Cardinal Plus обновлён до …» (один раз)."""
    saved = _load_saved()
    if saved.get("installed") != plus_version.VERSION or saved.get("announced"):
        return False
    _broadcast(cardinal, f"✅ <b>Cardinal Plus обновлён до {plus_version.VERSION}</b> (было {html.escape(str(saved.get('previous') or '?'))}).")
    saved["announced"] = True
    _save(saved)
    return True


def _loop(cardinal) -> None:
    time.sleep(10)
    try:
        announce_installed(cardinal)
    except Exception:
        logger.debug("TRACEBACK", exc_info=True)
    time.sleep(FIRST_CHECK)
    while True:
        try:
            check(force=True)
            notify_if_new(cardinal)
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
        time.sleep(CHECK_EVERY)


def start(cardinal) -> None:
    """Фоновая проверка обновлений (вызывается при запуске приложения)."""
    if not repo():
        logger.debug("Cardinal Plus: проверка обновлений выключена (UPDATE_REPO не указан).")
        return
    threading.Thread(target=_loop, args=(cardinal,), daemon=True, name="plus-update").start()


NOT_CONFIGURED = ("ℹ️ Это <b>Cardinal Plus</b> {v}. Проверка обновлений в этой сборке не настроена — "
                  "новую версию скачайте там же, где взяли эту.")


def tg_check(tgbot, m) -> None:
    """/check_updates: есть ли новая версия Cardinal Plus."""
    if m.from_user.id not in tgbot.authorized_users:
        return
    if not repo():
        tgbot.bot.send_message(m.chat.id, NOT_CONFIGURED.format(v=plus_version.VERSION), parse_mode="HTML")
        return
    st = check(force=True)
    if st["available"]:
        notes = _notes(st["latest"]["notes"])
        text = (f"🆕 Доступна <b>Cardinal Plus {html.escape(st['latest']['version'])}</b> (у вас {plus_version.VERSION})"
                + (f"\n\n{notes}" if notes else "") + "\n\nЧтобы обновиться, отправьте /update")
    elif st["error"]:
        text = f"❌ {html.escape(st['error'])}"
    else:
        text = f"✅ У вас последняя версия Cardinal Plus {plus_version.VERSION}."
    tgbot.bot.send_message(m.chat.id, text, parse_mode="HTML", disable_web_page_preview=True)


def tg_update(tgbot, m) -> None:
    """/update: поставить новую версию Cardinal Plus (не обычный Cardinal)."""
    if m.from_user.id not in tgbot.authorized_users:
        return
    if not repo():
        tgbot.bot.send_message(m.chat.id, NOT_CONFIGURED.format(v=plus_version.VERSION), parse_mode="HTML")
        return
    st = check(force=True)
    if not st["available"]:
        tgbot.bot.send_message(m.chat.id, f"❌ {html.escape(st['error'])}" if st["error"]
                               else f"✅ У вас последняя версия Cardinal Plus {plus_version.VERSION}.", parse_mode="HTML")
        return
    v = st["latest"]["version"]
    tgbot.bot.send_message(m.chat.id, f"⏳ Ставлю Cardinal Plus {html.escape(v)}… Настройки и плагины не тронутся.")

    def run():
        try:
            r = install(restart=False)
        except UpdateError as e:
            tgbot.bot.send_message(m.chat.id, f"❌ {e}\n\nНичего не сломалось — работает прежняя версия.")
            return
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
            tgbot.bot.send_message(m.chat.id, "❌ Обновление не удалось. Ничего не сломалось — работает прежняя версия.")
            return
        tgbot.bot.send_message(m.chat.id, f"✅ Cardinal Plus {r['to']} установлен. Перезапускаю Cardinal — через полминуты всё заработает."
                               + ("" if r["libraries"] else "\n\n⚠️ Новые библиотеки поставить не удалось — запустите Setup.bat."))
        _stage("restart")
        from webapp import plugin_installer
        plugin_installer.restart(delay=2)

    threading.Thread(target=run, daemon=True, name="plus-update-install").start()
