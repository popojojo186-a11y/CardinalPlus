"""
Резервная копия Cardinal+ одним файлом: настройки (configs), данные приложения и плагинов (storage),
товары автовыдачи (storage/products) и сами плагины (plugins). Файл зашифрован паролем —
в нём golden_key и токен бота, без пароля его не прочитать.

Формат: b"CPBK1" + соль (16) + число итераций (4) + nonce (16) + подпись HMAC (32) + зашифрованный zip.
Шифрование — PBKDF2-SHA256 → ключ, поток SHA-256 в режиме счётчика, подпись HMAC-SHA256.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import struct
import time
import zipfile

logger = logging.getLogger("FPC.webapp")

MAGIC = b"CPBK1"
ITERATIONS = 200_000
MIN_PASSWORD = 8
MAX_FILE = 8 * 1024 * 1024       # отдельный файл больше 8 МБ не берём (логи, кэши)
MAX_TOTAL = 60 * 1024 * 1024
ROOTS = ("configs", "storage", "plugins")
SKIP_DIRS = {"__pycache__", "logs", "backups", "plugin_backups"}
SKIP_EXT = {".pyc", ".log", ".tmp", ".db", ".db-journal", ".cpbak"}  # архив чатов (.db) можно собрать заново
SAFETY_DIR = os.path.join("storage", "backups")


class BackupError(Exception):
    pass


def _keys(password: str, salt: bytes, iterations: int) -> tuple[bytes, bytes]:
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=64)
    return k[:32], k[32:]


def _xor_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    blocks = (len(data) + 31) // 32
    stream = b"".join(hashlib.sha256(key + nonce + struct.pack(">Q", i)).digest() for i in range(blocks))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big") if data else b""


def encrypt(data: bytes, password: str) -> bytes:
    if len(password or "") < MIN_PASSWORD:
        raise BackupError(f"Пароль — не короче {MIN_PASSWORD} символов.")
    salt, nonce = os.urandom(16), os.urandom(16)
    enc, mac_key = _keys(password, salt, ITERATIONS)
    body = _xor_stream(enc, nonce, data)
    head = MAGIC + salt + struct.pack(">I", ITERATIONS) + nonce
    mac = hmac.new(mac_key, head + body, hashlib.sha256).digest()
    return head + mac + body


def decrypt(blob: bytes, password: str) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < 5 + 16 + 4 + 16 + 32:
        raise BackupError("Это не резервная копия Cardinal+.")
    salt = blob[5:21]
    iterations = struct.unpack(">I", blob[21:25])[0]
    nonce = blob[25:41]
    mac, body = blob[41:73], blob[73:]
    if not 1000 <= iterations <= 5_000_000:
        raise BackupError("Файл повреждён.")
    enc, mac_key = _keys(password or "", salt, iterations)
    if not hmac.compare_digest(mac, hmac.new(mac_key, blob[:41] + body, hashlib.sha256).digest()):
        raise BackupError("Неверный пароль или файл повреждён.")
    return _xor_stream(enc, nonce, body)


def collect(base: str = ".") -> list[str]:
    files, total = [], 0
    for root in ROOTS:
        top = os.path.join(base, root)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                path = os.path.join(dirpath, name)
                if os.path.splitext(name)[1].lower() in SKIP_EXT or name.endswith(".tmp"):
                    continue
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size > MAX_FILE or total + size > MAX_TOTAL:
                    continue
                total += size
                files.append(os.path.relpath(path, base).replace("\\", "/"))
    return sorted(files)


def make(password: str, base: str = ".") -> tuple[bytes, dict]:
    files = collect(base)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cardinal_plus_backup.txt", f"Резервная копия Cardinal+ от {time.strftime('%d.%m.%Y %H:%M')}\n"
                                                f"Файлов: {len(files)}\n")
        for rel in files:
            try:
                z.write(os.path.join(base, rel), rel)
            except OSError:
                logger.debug("TRACEBACK", exc_info=True)
    raw = buf.getvalue()
    return encrypt(raw, password), {"files": len(files), "size": len(raw)}


def _safe_names(z: zipfile.ZipFile) -> list[str]:
    names = []
    for info in z.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or name == "cardinal_plus_backup.txt":
            continue
        parts = name.split("/")
        if name.startswith("/") or ".." in parts or ":" in name or parts[0] not in ROOTS:
            raise BackupError(f"В копии есть посторонний файл: {name[:80]}")
        names.append(name)
    return names


def inspect(blob: bytes, password: str) -> dict:
    data = decrypt(blob, password)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = _safe_names(z)
            note = z.read("cardinal_plus_backup.txt").decode("utf-8", "replace") if "cardinal_plus_backup.txt" in z.namelist() else ""
    except zipfile.BadZipFile:
        raise BackupError("Файл повреждён.")
    return {"files": len(names), "plugins": sum(1 for n in names if n.startswith("plugins/") and n.endswith(".py")),
            "configs": sum(1 for n in names if n.startswith("configs/")), "note": note.splitlines()[0] if note else ""}


def restore(blob: bytes, password: str, base: str = ".") -> dict:
    """Распаковывает копию поверх текущих файлов. Перед этим текущие файлы сохраняются в storage/backups."""
    data = decrypt(blob, password)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = _safe_names(z)
    except zipfile.BadZipFile:
        raise BackupError("Файл повреждён.")
    # страховка: текущее состояние — тем же паролем, чтобы можно было вернуться
    os.makedirs(os.path.join(base, SAFETY_DIR), exist_ok=True)
    safety_blob, _ = make(password, base)
    safety = os.path.join(SAFETY_DIR, f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}.cpbak")
    with open(os.path.join(base, safety), "wb") as f:
        f.write(safety_blob)
    written = 0
    with z:
        for name in names:
            target = os.path.join(base, *name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".restore-tmp"
            with open(tmp, "wb") as f:
                f.write(z.read(name))
            os.replace(tmp, target)
            written += 1
    logger.info(f"Mini App: восстановлено из резервной копии файлов: {written}. Прежние файлы — {safety}")
    return {"files": written, "safety": safety.replace("\\", "/")}
