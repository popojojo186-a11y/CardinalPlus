"""
Склад автовыдачи для приложения.

Работает с теми же файлами, что и Telegram-бот Cardinal, поэтому всё совместимо в обе стороны:
- товарные файлы — storage/products/*.txt (одна строка = один товар; «\\n» внутри строки — перенос);
- лоты с автовыдачей — configs/auto_delivery.cfg (секция = название лота, productsFileName = файл с товарами).

Чтение и запись файлов идут под тем же замком, что и выдача товара в Cardinal
(cardinal_tools.get_products_file_lock), поэтому одновременная продажа ничего не сломает.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import TYPE_CHECKING

from Utils import cardinal_tools

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

PRODUCTS_DIR = os.path.join("storage", "products")
AD_PATH = "configs/auto_delivery.cfg"
SETTINGS_PATH = os.path.join("storage", "cache", "webapp_stock.json")
NAME_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9_\- ]{1,60}")  # те же правила, что у Telegram-бота Cardinal
DEFAULT_LOW = 5          # «заканчивается», если осталось столько или меньше
MAX_ADD_LINES = 5000     # товаров за один раз
MAX_LINE = 4000          # символов в одном товаре
MAX_VIEW = 1000          # сколько товаров показывать в списке
MAX_RESPONSE = 3000
DEFAULT_RESPONSE = "Спасибо за покупку, $username!\n\nВот твой товар:\n$product"


class StockError(Exception):
    pass


def _clean_lines(text: str) -> list[str]:
    return [ln.strip() for ln in str(text or "").replace("\r", "").split("\n") if ln.strip()]


class StockService:
    def __init__(self, cardinal: Cardinal):
        self.c = cardinal
        self._lock = threading.RLock()
        self.settings = self._load_settings()
        self._installed = False

    # ---------- настройки склада (порог «заканчивается», какие уведомления уже отправлены) ----------
    @staticmethod
    def _load_settings() -> dict:
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"low": dict(data.get("low") or {}), "notified": dict(data.get("notified") or {})}
        except (OSError, ValueError, TypeError):
            pass
        return {"low": {}, "notified": {}}

    def _save_settings(self) -> None:
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SETTINGS_PATH)
        except OSError:
            logger.debug("TRACEBACK", exc_info=True)

    def low(self, file: str) -> int:
        try:
            return max(0, int(self.settings["low"].get(file, DEFAULT_LOW)))
        except (TypeError, ValueError):
            return DEFAULT_LOW

    # ---------- файлы ----------
    @staticmethod
    def _file_name(name: str) -> str:
        name = str(name or "").strip()
        if name.lower().endswith(".txt"):
            name = name[:-4].strip()
        if not NAME_RE.fullmatch(name):
            raise StockError("Название файла: буквы, цифры, пробел, «-» и «_», до 60 символов.")
        return name + ".txt"

    @staticmethod
    def _path(file: str) -> str:
        return os.path.join(PRODUCTS_DIR, file)

    def _existing(self, name: str) -> tuple[str, str]:
        file = self._file_name(name)
        path = self._path(file)
        if not os.path.isfile(path):
            raise StockError("Такого файла с товарами нет — обновите страницу.")
        return file, path

    @staticmethod
    def _files() -> list[str]:
        os.makedirs(PRODUCTS_DIR, exist_ok=True)
        return sorted((f for f in os.listdir(PRODUCTS_DIR) if f.endswith(".txt") and os.path.isfile(os.path.join(PRODUCTS_DIR, f))),
                      key=str.lower)

    @staticmethod
    def _read(path: str) -> list[str]:
        """Товары файла (пустые строки Cardinal тоже пропускает). Вызывать под замком файла."""
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [ln for ln in f.read().split("\n") if ln]

    @staticmethod
    def _write(path: str, items: list[str]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(items))

    def _status(self, file: str, count: int) -> str:
        return "empty" if count == 0 else "low" if count <= self.low(file) else "ok"

    # ---------- общий вид ----------
    def _ad(self):
        return self.c.AD_CFG

    def _save_ad(self) -> None:
        self.c.save_config(self.c.AD_CFG, AD_PATH)

    def _ad_lots(self) -> list[dict]:
        ad = self._ad()
        result = []
        for title in ad.sections():
            sec = ad[title]
            result.append({
                "title": title,
                "file": sec.get("productsFileName") or None,
                "response": sec.get("response", ""),
                "disabled": sec.getboolean("disable", fallback=False),
                "multi_off": sec.getboolean("disableMultiDelivery", fallback=False),
            })
        return result

    def _profile_lots(self) -> list[dict]:
        profile = getattr(self.c, "profile", None) or getattr(self.c, "tg_profile", None)
        items = []
        try:
            for lot in (profile.get_lots() if profile else []):
                title = lot.description or getattr(lot, "title", None)
                if not title:
                    continue
                sub = getattr(lot, "subcategory", None)
                items.append({"id": str(lot.id), "title": title, "sub": getattr(sub, "fullname", "") or ""})
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
        return items

    def counts(self) -> dict[str, int]:
        return {f: cardinal_tools.count_products(self._path(f)) for f in self._files()}

    def alerts(self) -> dict:
        """Для значка в меню: сколько файлов пусты и сколько заканчиваются."""
        empty = low = 0
        try:
            for f, n in self.counts().items():
                s = self._status(f, n)
                empty += s == "empty"
                low += s == "low"
        except OSError:
            logger.debug("TRACEBACK", exc_info=True)
        return {"empty": empty, "low": low}

    def overview(self) -> dict:
        lots = self._ad_lots()
        counts = self.counts()
        by_file: dict[str, list[str]] = {}
        for lot in lots:
            if lot["file"]:
                by_file.setdefault(lot["file"], []).append(lot["title"])
            lot["count"] = counts.get(lot["file"]) if lot["file"] else None
            lot["missing"] = bool(lot["file"]) and lot["file"] not in counts
        files = [{"name": f[:-4], "file": f, "count": n, "low": self.low(f), "status": self._status(f, n),
                  "lots": by_file.get(f, [])} for f, n in counts.items()]
        linked = {lot["title"] for lot in lots}
        profile = [p for p in self._profile_lots() if p["title"] not in linked]
        return {
            "files": files,
            "lots": lots,
            "free_lots": profile,
            "autodelivery": bool(getattr(self.c, "autodelivery_enabled", True)),
            "multidelivery": bool(getattr(self.c, "multidelivery_enabled", True)),
            "total": sum(counts.values()),
            "empty": sum(1 for f in files if f["status"] == "empty"),
            "low_count": sum(1 for f in files if f["status"] == "low"),
        }

    def items(self, name: str, q: str = "") -> dict:
        file, path = self._existing(name)
        with cardinal_tools.get_products_file_lock(path):
            items = self._read(path)
        q = (q or "").strip().lower()
        found = [{"i": i, "text": t} for i, t in enumerate(items) if not q or q in t.lower()]
        lots = [lot["title"] for lot in self._ad_lots() if lot["file"] == file]
        return {"name": file[:-4], "file": file, "count": len(items), "items": found[:MAX_VIEW], "found": len(found),
                "low": self.low(file), "status": self._status(file, len(items)), "lots": lots}

    # ---------- изменения файлов ----------
    def create(self, name: str) -> dict:
        file = self._file_name(name)
        path = self._path(file)
        os.makedirs(PRODUCTS_DIR, exist_ok=True)
        if os.path.exists(path):
            raise StockError(f"Файл «{file[:-4]}» уже есть.")
        with cardinal_tools.get_products_file_lock(path):
            self._write(path, [])
        logger.info(f"Mini App: создан товарный файл {file}")
        return {"name": file[:-4], "file": file}

    def add(self, name: str, text: str, dedupe: bool = True) -> dict:
        file, path = self._existing(name)
        new = _clean_lines(text)
        if not new:
            raise StockError("Вставьте товары — каждый с новой строки.")
        if len(new) > MAX_ADD_LINES:
            raise StockError(f"За один раз — не больше {MAX_ADD_LINES} товаров.")
        if any(len(x) > MAX_LINE for x in new):
            raise StockError(f"Один из товаров длиннее {MAX_LINE} символов — проверьте, что каждый товар на своей строке.")
        with cardinal_tools.get_products_file_lock(path):
            items = self._read(path)
            skipped = 0
            if dedupe:
                seen = set(items)
                unique = []
                for x in new:
                    if x in seen:
                        skipped += 1
                        continue
                    seen.add(x)
                    unique.append(x)
                new = unique
            if new:
                self._write(path, items + new)
            total = len(items) + len(new)
        self._reset_notified(file, total)
        logger.info(f"Mini App: в {file} добавлено товаров: {len(new)}" + (f", повторов пропущено: {skipped}" if skipped else ""))
        return {"added": len(new), "skipped": skipped, "count": total}

    def remove(self, name: str, index: int, text: str) -> dict:
        file, path = self._existing(name)
        with cardinal_tools.get_products_file_lock(path):
            items = self._read(path)
            if not (0 <= index < len(items)) or items[index] != text:
                # пока страница была открыта, товар могли продать — ищем его по тексту
                if text not in items:
                    raise StockError("Этого товара уже нет в файле — возможно, его только что выдали покупателю.")
                index = items.index(text)
            items.pop(index)
            self._write(path, items)
        logger.info(f"Mini App: из {file} удалён товар")
        return {"count": len(items)}

    def clear(self, name: str) -> dict:
        file, path = self._existing(name)
        with cardinal_tools.get_products_file_lock(path):
            n = len(self._read(path))
            self._write(path, [])
        logger.info(f"Mini App: файл {file} очищен ({n} шт.)")
        return {"removed": n}

    def delete(self, name: str) -> dict:
        file, path = self._existing(name)
        used = [lot["title"] for lot in self._ad_lots() if lot["file"] == file]
        if used:
            raise StockError("Файл подключён к лотам: " + ", ".join(used[:3]) + ("…" if len(used) > 3 else "") +
                             ". Сначала подключите им другой файл или отключите автовыдачу.")
        with cardinal_tools.get_products_file_lock(path):
            os.remove(path)
        self.settings["low"].pop(file, None)
        self.settings["notified"].pop(file, None)
        self._save_settings()
        logger.info(f"Mini App: товарный файл {file} удалён")
        return {"ok": True}

    def set_low(self, name: str, value) -> dict:
        file, _ = self._existing(name)
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise StockError("Нужно целое число.")
        if not 0 <= value <= 100000:
            raise StockError("Число от 0 до 100000.")
        self.settings["low"][file] = value
        self._save_settings()
        return {"low": value}

    # ---------- лоты с автовыдачей ----------
    def _section(self, title: str):
        title = str(title or "")
        if title not in self._ad().sections():
            raise StockError("Этого лота уже нет в автовыдаче — обновите страницу.")
        return self._ad()[title]

    def _check_response(self, response: str, file: str | None) -> str:
        response = str(response or "").replace("\r", "").strip()
        if not response:
            raise StockError("Текст выдачи пустой.")
        if len(response) > MAX_RESPONSE:
            raise StockError(f"Текст выдачи длиннее {MAX_RESPONSE} символов.")
        if file and "$product" not in response:
            raise StockError("В тексте выдачи нет $product — покупатель не получит товар из файла.")
        return response

    def link(self, title: str, file: str | None = None, new_file: str | None = None, response: str | None = None) -> dict:
        title = str(title or "").strip()
        if not title or len(title) > 500 or "\n" in title or "[" in title or "]" in title:
            raise StockError("Укажите название лота так, как оно написано на FunPay.")
        with self._lock:
            ad = self._ad()
            if title in ad.sections():
                raise StockError("Этот лот уже подключён к автовыдаче.")
            target = None
            if new_file:
                target = self.create(new_file)["file"]
            elif file:
                target, _ = self._existing(file)
            if not response:
                response = DEFAULT_RESPONSE if target else "Спасибо за покупку, $username!"
            response = self._check_response(response, target)
            ad.add_section(title)
            ad.set(title, "response", response)
            if target:
                ad.set(title, "productsFileName", target)
            self._save_ad()
        logger.info(f"Mini App: лот «{title}» подключён к автовыдаче" + (f" (файл {target})" if target else ""))
        return {"title": title, "file": target}

    def update(self, title: str, data: dict) -> dict:
        with self._lock:
            sec = self._section(title)
            ad = self._ad()
            file = sec.get("productsFileName") or None
            if "file" in data:
                if data.get("file"):
                    file, _ = self._existing(data["file"])
                else:
                    file = None
            response = data["response"] if "response" in data else sec.get("response", "")
            response = self._check_response(response, file)
            ad.set(title, "response", response)
            if file:
                ad.set(title, "productsFileName", file)
            elif ad.has_option(title, "productsFileName"):
                ad.remove_option(title, "productsFileName")
            if "disabled" in data:
                ad.set(title, "disable", "1" if data.get("disabled") else "0")
            if "multi_off" in data:
                ad.set(title, "disableMultiDelivery", "1" if data.get("multi_off") else "0")
            self._save_ad()
        logger.info(f"Mini App: изменена автовыдача лота «{title}»")
        return {"ok": True}

    def unlink(self, title: str) -> dict:
        with self._lock:
            self._section(title)
            self._ad().remove_section(title)
            self._save_ad()
        logger.info(f"Mini App: лот «{title}» отключён от автовыдачи")
        return {"ok": True}

    # ---------- уведомление «товар заканчивается» ----------
    def install(self) -> None:
        handlers = getattr(self.c, "post_delivery_handlers", None)
        if self._installed or handlers is None:
            return

        def on_delivery(cardinal, event):
            self.on_delivery(event)

        on_delivery.plugin_uuid = None  # встроенный обработчик, работает всегда
        handlers.append(on_delivery)
        self._installed = True

    def _reset_notified(self, file: str, count: int) -> None:
        if self._status(file, count) == "ok" and self.settings["notified"].pop(file, None) is not None:
            self._save_settings()

    def on_delivery(self, event) -> None:
        try:
            if not getattr(event, "delivered", False):
                return
            sec = getattr(event, "config_section_obj", None)
            file = sec.get("productsFileName") if sec is not None else None
            left = getattr(event, "goods_left", None)
            if not file or left is None or left < 0:
                return
            status = self._status(file, left)
            if status == "ok":
                self._reset_notified(file, left)
                return
            if self.settings["notified"].get(file) == status:
                return  # уже сообщали
            self.settings["notified"][file] = status
            self._save_settings()
            tg = getattr(self.c, "telegram", None)
            if tg is None:
                return
            from tg_bot import utils as tg_utils
            name = file[:-4]
            text = (f"📦 <b>Товар закончился</b>: <code>{tg_utils.escape(name)}</code>\n"
                    f"Автовыдача по этому файлу не сработает, пока не добавите товары." if status == "empty" else
                    f"📦 <b>Товар заканчивается</b>: <code>{tg_utils.escape(name)}</code>\n"
                    f"Осталось: <b>{left}</b> шт.")
            text += "\n\nПополнить можно в приложении Cardinal+ → «Склад»."
            threading.Thread(target=tg.send_notification, args=(text, None, tg_utils.NotificationTypes.delivery),
                             daemon=True).start()
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)
