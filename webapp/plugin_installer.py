"""
Установка плагинов из приложения.

1. inspect() читает файл, НЕ запуская его: достаёт название, версию, автора, UUID и ищет в коде то,
   на что стоит обратить внимание (чтение golden_key, запуск команд, скрытый код).
2. install() кладёт файл в plugins/. Новый плагин сразу подключается без перезапуска Cardinal.
   Обновление уже установленного плагина вступает в силу после перезапуска (старая копия сохраняется).
"""
from __future__ import annotations

import ast
import datetime
import logging
import os
import re
import shutil
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

PLUGINS_DIR = "plugins"
BACKUP_DIR = os.path.join("storage", "plugin_backups")
MAX_SIZE = 700 * 1024
REQUIRED = ("NAME", "VERSION", "DESCRIPTION", "CREDITS", "SETTINGS_PAGE", "UUID", "BIND_TO_DELETE")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
START_BINDS = ("BIND_TO_PRE_INIT", "BIND_TO_POST_INIT", "BIND_TO_PRE_START", "BIND_TO_POST_START")
BACKUP_RE = re.compile(r"^[\w\-]+\.(?:deleted-)?(\d{8}-\d{6})(?:-\d+)?\.py$", re.UNICODE)

# Обновления, которые уже записаны в plugins/, но заработают после перезапуска: uuid -> {"version", "time"}.
# Хранится в памяти — после перезапуска Cardinal список сам становится пустым.
PENDING: dict = {}

_lock = threading.Lock()


class InstallError(Exception):
    pass


# ───────────────────────────── разбор файла без запуска ─────────────────────────────
def _safe_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    stem, ext = os.path.splitext(base)
    if ext.lower() != ".py":
        raise InstallError("Нужен файл плагина с расширением .py")
    stem = re.sub(r"[^\w\-]", "_", stem, flags=re.UNICODE).strip("_.")[:60]
    if not stem:
        stem = "plugin"
    if stem[0].isdigit():
        stem = "p_" + stem
    return stem + ".py"


def _literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _fields(tree: ast.Module) -> dict:
    found = {}
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for t in targets:
            if isinstance(t, ast.Name):
                found[t.id] = value
    return found


def _checks(source: str, tree: ast.Module) -> list[dict]:
    """Подсказки «на что обратить внимание». Это не антивирус: честный плагин тоже может что-то из этого делать."""
    names, attrs, calls = set(), set(), set()
    builtin_calls = set()  # exec(...), eval(...), builtins.exec(...) — но не re.compile(...) и не cursor.execute(...)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            names.update(m.split(".")[0] for m in mods)
        if isinstance(node, ast.Call):
            f = node.func
            calls.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
            if isinstance(f, ast.Name):
                builtin_calls.add(f.id)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("builtins", "__builtins__"):
                builtin_calls.add(f.attr)

    low = source.lower()
    result = []
    if "golden_key" in low or "goldenkey" in low:
        result.append({"level": "danger", "text": "Читает golden_key — ключ входа в твой аккаунт FunPay. "
                                                  "Честным плагинам он почти никогда не нужен."})
    if "_main.cfg" in low or "tg_authorized_users" in low or "configs/" in low and "token" in low:
        result.append({"level": "danger", "text": "Открывает файлы настроек Cardinal, где лежат ключи и токен бота."})
    if {"exec", "eval", "compile", "__import__"} & builtin_calls or "marshal" in names:
        result.append({"level": "danger", "text": "Запускает код, спрятанный внутри строки. Так часто прячут вредоносный код."})
    long_lines = [ln for ln in source.splitlines() if len(ln) > 1500]
    if long_lines or re.search(r"[A-Za-z0-9+/=]{2000,}", source):
        result.append({"level": "danger", "text": "В коде есть очень длинные зашифрованные куски. Нормальный плагин так не пишут."})
    if {"subprocess", "ctypes", "winreg"} & names or {"system", "popen", "startfile", "spawnl", "spawnv"} & (calls | attrs):
        result.append({"level": "warn", "text": "Запускает программы или команды на компьютере."})
    net = {"requests", "urllib", "urllib3", "http", "aiohttp", "httpx", "socket", "websocket", "websockets"} & names
    if net:
        hosts = sorted({h for h in re.findall(r"https?://([a-z0-9.-]+)", low)
                        if not h.endswith(("funpay.com", "sfunpay.com", "telegram.org", "t.me", "github.com",
                                           "githubusercontent.com", "steampowered.com", "steamcommunity.com"))})[:4]
        where = f": {', '.join(hosts)}" if hosts else ""
        result.append({"level": "warn", "text": f"Отправляет запросы в интернет{where}."})
    if {"remove", "unlink", "rmtree", "rmdir"} & (calls | attrs):
        result.append({"level": "info", "text": "Может удалять файлы."})
    return result


def _ver(v) -> tuple | None:
    parts = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in parts[:6]) if parts else None


def compare_versions(new, current) -> str | None:
    """newer / same / older — или None, если версии не похожи на числа."""
    a, b = _ver(new), _ver(current)
    if a is None or b is None:
        return None if str(new) != str(current) else "same"
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return "newer" if a > b else "same" if a == b else "older"


def inspect(cardinal: Cardinal, filename: str, source: str, expect_uuid: str | None = None) -> dict:
    if not isinstance(source, str) or not source.strip():
        raise InstallError("Файл пустой.")
    if len(source.encode("utf-8")) > MAX_SIZE:
        raise InstallError("Файл слишком большой (больше 700 КБ).")
    safe_name = _safe_filename(filename)
    first = source.lstrip("﻿").split("\n", 1)[0]
    if first.startswith("#") and "noplug" in first.split():
        raise InstallError("Это вспомогательный файл, а не плагин (в первой строке стоит noplug).")
    try:
        tree = ast.parse(source, filename=safe_name)
    except SyntaxError as e:
        raise InstallError(f"В файле ошибка Python на строке {e.lineno}. Это не плагин или он повреждён.")

    raw = _fields(tree)
    missing = [f for f in REQUIRED if f not in raw]
    if missing:
        raise InstallError("Это не плагин Cardinal: в файле нет " + ", ".join(missing) + ".")
    val = {k: _literal(raw[k]) for k in ("NAME", "VERSION", "DESCRIPTION", "CREDITS", "UUID")}
    uuid = val["UUID"]
    if not isinstance(uuid, str) or not UUID_RE.match(uuid):
        raise InstallError("У плагина неправильный UUID. Cardinal не сможет его загрузить.")

    if expect_uuid and uuid.lower() != str(expect_uuid).lower():
        other = cardinal.plugins.get(uuid)
        raise InstallError(f"Это файл другого плагина — «{val['NAME'] or safe_name[:-3]}»"
                           + (" (он у вас уже установлен)" if other else "")
                           + ". Для обновления выберите новую версию этого же плагина.")
    existing = cardinal.plugins.get(uuid)
    target = existing.path if existing else os.path.join(PLUGINS_DIR, safe_name).replace("\\", "/")
    if not existing:
        stem, i = safe_name[:-3], 2
        while os.path.exists(target):
            target = os.path.join(PLUGINS_DIR, f"{stem}_{i}.py").replace("\\", "/")
            i += 1

    return {
        "uuid": uuid,
        "name": str(val["NAME"] or safe_name[:-3]),
        "version": str(val["VERSION"] or "?"),
        "description": str(val["DESCRIPTION"] or ""),
        "credits": str(val["CREDITS"] or ""),
        "has_ui": "WEBAPP" in raw,
        "update": bool(existing),
        "current_version": existing.version if existing else None,
        "version_cmp": compare_versions(val["VERSION"], existing.version) if existing else None,
        "pending_version": (PENDING.get(uuid) or {}).get("version"),
        "target": target,
        "checks": _checks(source, tree),
    }


# ───────────────────────────── установка ─────────────────────────────
def _backup(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst, i = os.path.join(BACKUP_DIR, f"{os.path.basename(path)[:-3]}.{stamp}.py"), 2
    while os.path.exists(dst):  # две копии в одну секунду не должны затирать друг друга
        dst, i = os.path.join(BACKUP_DIR, f"{os.path.basename(path)[:-3]}.{stamp}-{i}.py"), i + 1
    shutil.copy2(path, dst)
    return dst


def _write(path: str, source: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(source)
    os.replace(tmp, path)


def _hot_load(cardinal: Cardinal, path: str, uuid: str) -> None:
    """Подключает новый плагин так же, как Cardinal при запуске, только для одного файла."""
    from cardinal import PluginData
    from Utils import cardinal_tools

    file = os.path.basename(path)
    plugin, data = cardinal.load_plugin(file)
    if data["UUID"] != uuid:
        raise InstallError("UUID плагина изменился при загрузке.")
    if uuid in cardinal.disabled_plugins:
        cardinal.disabled_plugins.remove(uuid)
        cardinal_tools.cache_disabled_plugins(cardinal.disabled_plugins)
    cardinal.plugins[uuid] = PluginData(data["NAME"], data["VERSION"], data["DESCRIPTION"], data["CREDITS"], uuid,
                                        f"plugins/{file}", plugin, data["SETTINGS_PAGE"], data["BIND_TO_DELETE"],
                                        True, False)
    cardinal.add_handlers_from_plugin(plugin, uuid)

    # то, что Cardinal делает при запуске: init → post-init → start
    for name in START_BINDS:
        funcs = getattr(plugin, name, None) or []
        cardinal.run_handlers(list(funcs), (cardinal,))

    if cardinal.telegram:  # новые команды плагина — в меню бота
        threading.Thread(target=_refresh_commands, args=(cardinal,), daemon=True).start()


def _refresh_commands(cardinal: Cardinal) -> None:
    try:
        cardinal.telegram.setup_commands()
    except Exception:
        logger.debug("TRACEBACK", exc_info=True)


def install(cardinal: Cardinal, filename: str, source: str, expect_uuid: str | None = None) -> dict:
    with _lock:
        info = inspect(cardinal, filename, source, expect_uuid)
        path = info["target"]
        if info["update"]:
            backup = _backup(path)
            _write(path, source)
            PENDING[info["uuid"]] = {"version": info["version"], "time": int(time.time())}
            logger.info(f"Mini App: обновлён плагин {info['name']} до v{info['version']} ({path}), старая версия: {backup}")
            return {**info, "loaded": False, "restart_required": True}

        _write(path, source)
        try:
            _hot_load(cardinal, path, info["uuid"])
        except Exception as e:
            cardinal.plugins.pop(info["uuid"], None)
            try:
                os.remove(path)
            except OSError:
                pass
            logger.error(f"Mini App: плагин {info['name']} не загрузился и удалён.")
            logger.debug("TRACEBACK", exc_info=True)
            raise InstallError(f"Плагин не запустился: {type(e).__name__}: {str(e)[:200]}. Файл не сохранён.")
        logger.info(f"Mini App: установлен плагин {info['name']} v{info['version']} ({path})")
        return {**info, "loaded": True, "restart_required": False}


# ───────────────────────────── удаление ─────────────────────────────
def delete(cardinal: Cardinal, uuid: str) -> dict:
    """
    Удаляет плагин так же, как кнопка в боте Cardinal, но файл не стирается насовсем,
    а переносится в storage/plugin_backups — его можно вернуть. Настройки плагина остаются.
    """
    from Utils import cardinal_tools

    with _lock:
        p = cardinal.plugins.get(uuid)
        if p is None:
            raise InstallError("Плагин не найден.")
        if p.delete_handler:  # то же, что делает Cardinal при удалении из бота
            try:
                p.delete_handler(cardinal, None)
            except Exception:
                logger.error(f"Mini App: ошибка в обработчике удаления плагина {p.name}")
                logger.debug("TRACEBACK", exc_info=True)

        backup = None
        if os.path.exists(p.path):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = os.path.join(BACKUP_DIR, f"{os.path.basename(p.path)[:-3]}.deleted-{stamp}.py")
            shutil.move(p.path, backup)

        p.enabled = False  # обработчики плагина больше не вызываются, полностью он выгрузится после перезапуска
        cardinal.plugins.pop(uuid, None)
        for attr, save in (("disabled_plugins", cardinal_tools.cache_disabled_plugins),
                           ("pinned_plugins", cardinal_tools.cache_pinned_plugins)):
            items = getattr(cardinal, attr, None)
            if isinstance(items, list) and uuid in items:
                items.remove(uuid)
                try:
                    save(items)
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
        if cardinal.telegram:
            for command in list(p.commands):  # убрать команды плагина из меню бота
                getattr(cardinal.telegram, "commands", {}).pop(command, None)
            threading.Thread(target=_refresh_commands, args=(cardinal,), daemon=True).start()

        logger.info(f"Mini App: удалён плагин {p.name} ({p.path}), копия: {backup}")
        return {"name": p.name, "backup": backup.replace("\\", "/") if backup else None}


# ───────────────────────────── прошлые версии ─────────────────────────────
def backups(cardinal: Cardinal, uuid: str, limit: int = 10) -> list[dict]:
    """Сохранённые копии этого плагина (их делает обновление), новые сверху."""
    p = cardinal.plugins.get(uuid)
    if p is None or not os.path.isdir(BACKUP_DIR):
        return []
    stem = os.path.basename(p.path)[:-3]
    out = []
    for name in os.listdir(BACKUP_DIR):
        m = BACKUP_RE.match(name)
        if not (m and name.startswith(stem + ".")):
            continue
        path = os.path.join(BACKUP_DIR, name)
        try:  # когда сделана копия — по имени файла (время изменения у копии остаётся от оригинала)
            saved = int(datetime.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").timestamp())
        except ValueError:
            saved = int(os.path.getmtime(path))
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = _fields(ast.parse(f.read()))
        except Exception:
            continue
        if _literal(raw.get("UUID")) != uuid:
            continue
        out.append({"file": name, "version": str(_literal(raw.get("VERSION")) or "?"), "time": saved})
    out.sort(key=lambda x: (-x["time"], x["file"]), reverse=False)
    return out[:limit]


def rollback(cardinal: Cardinal, uuid: str, file: str) -> dict:
    """Вернуть сохранённую копию. Текущая версия при этом тоже сохраняется — откат можно отменить."""
    name = os.path.basename(str(file or ""))
    if not BACKUP_RE.match(name) or not any(b["file"] == name for b in backups(cardinal, uuid, limit=1000)):
        raise InstallError("Эта копия не найдена — обновите страницу.")
    with open(os.path.join(BACKUP_DIR, name), "r", encoding="utf-8") as f:
        source = f.read()
    p = cardinal.plugins[uuid]
    result = install(cardinal, os.path.basename(p.path), source, expect_uuid=uuid)
    logger.info(f"Mini App: плагин {p.name} возвращён к копии {name}")
    return result


# ───────────────────────────── перезапуск ─────────────────────────────
def restart(delay: float = 1.0) -> None:
    """Перезапускает Cardinal, как команда /restart в боте. Перед этим закрывает туннель."""

    def run():
        time.sleep(delay)
        try:
            import webapp
            tunnel = webapp._state.get("tunnel")
            if tunnel:
                tunnel.stop()
                if tunnel.process:
                    try:
                        tunnel.process.wait(timeout=5)
                    except Exception:
                        pass
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
        from Utils import cardinal_tools
        logger.info("Mini App: перезапуск Cardinal по запросу из приложения.")
        cardinal_tools.restart_program()

    threading.Thread(target=run, daemon=True, name="cp-restart").start()
