"""
Управление своими лотами: список по играм, включение/выключение, цена, массовые изменения.

Список берётся со страниц «Мои предложения» каждой подкатегории (lots/<id>/trade) — там видны
и активные, и выключенные лоты. Изменения делаются так же, как в самом Cardinal:
get_lot_fields -> правка -> save_lot.

Цена в редакторе лота — это «ваша» цена (сколько получите вы). На витрине покупатель видит
цену с комиссией FunPay, поэтому массовые изменения считаются от цены из редактора.
"""
from __future__ import annotations

import json
import logging
import math
import os
import secrets
import threading
import time
from typing import TYPE_CHECKING

from FunPayAPI.common.enums import SubCategoryTypes

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

SUBCATS_PATH = "storage/cache/webapp_lot_subcategories.json"
LIST_TTL = 60
REQUEST_PAUSE = 0.6          # пауза между запросами к FunPay при массовых изменениях
MAX_BULK = 300


class LotsError(Exception):
    pass


class LotsService:
    def __init__(self, cardinal: Cardinal):
        self.crd = cardinal
        self._lock = threading.RLock()
        self._funpay_lock = threading.Lock()   # не больше одной «тяжёлой» операции с FunPay одновременно
        self._cache: tuple[float, dict] | None = None
        self.jobs: dict[str, dict] = {}
        # Цена из редактора лота (то, что получает продавец) и коэффициент «цена на витрине / цена продавца»
        # по подкатегориям. Нужны, чтобы предпросмотр массовых изменений считался от правильной цены.
        self._my_price: dict[int, float] = {}
        self._list_price: dict[int, tuple[int, float]] = {}   # lot_id -> (subcategory_id, цена в списке)
        self._coef: dict[int, float] = {}
        self._demo = None
        try:
            from webapp import config as webapp_config
            if webapp_config.load().get("demo_lots"):
                from webapp.demo_lots import DemoAccount
                self._demo = DemoAccount()
        except Exception:
            logger.debug("TRACEBACK", exc_info=True)

    def _remember_fields(self, lot_id: int, my_price: float | None):
        if my_price is None:
            return
        self._my_price[lot_id] = my_price
        lp = self._list_price.get(lot_id)
        if lp and my_price > 0 and lp[1] > 0:
            self._coef[lp[0]] = lp[1] / my_price

    # ---------- подкатегории ----------
    # ---------- демо-режим ----------
    @property
    def demo(self) -> bool:
        return self._demo is not None

    def set_demo(self, enabled: bool):
        from webapp import config as webapp_config
        from webapp.demo_lots import DemoAccount
        if any(j["status"] == "running" for j in self.jobs.values()):
            raise LotsError("Сейчас идёт массовое изменение — дождитесь его окончания.")
        with self._lock:
            self._demo = DemoAccount() if enabled else None
            self._my_price.clear(); self._list_price.clear(); self._coef.clear()
            self._cache = None
        cfg = webapp_config.load()
        cfg["demo_lots"] = bool(enabled)
        webapp_config.save(cfg)

    def _acc(self):
        return self._demo or self.crd.account

    def _known_subcategories(self) -> set[int]:
        if self._demo is not None:
            return self._demo.subcategory_ids()
        ids: set[int] = set()
        if os.path.exists(SUBCATS_PATH):
            try:
                with open(SUBCATS_PATH, "r", encoding="utf-8") as f:
                    ids.update(int(i) for i in json.load(f))
            except (OSError, ValueError, TypeError):
                pass
        profile = self.crd.profile
        if profile is not None:
            try:
                for sub in profile.get_sorted_lots(2).keys():
                    if sub.type is SubCategoryTypes.COMMON:
                        ids.add(int(sub.id))
            except Exception:
                logger.debug("TRACEBACK", exc_info=True)
        return ids

    def _remember_subcategories(self, ids: set[int]):
        os.makedirs(os.path.dirname(SUBCATS_PATH), exist_ok=True)
        with open(SUBCATS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f)

    def add_subcategory(self, sub_id: int):
        """Пользователь может вручную добавить подкатегорию, где лежат только выключенные лоты."""
        if self.demo:
            raise LotsError("В демо-режиме разделы добавлять не нужно — выключите демо-режим.")
        acc = self._acc()
        sub = acc.get_subcategory(SubCategoryTypes.COMMON, sub_id)
        if sub is None:
            raise LotsError("Такой подкатегории нет на FunPay.")
        ids = self._known_subcategories()
        ids.add(sub_id)
        self._remember_subcategories(ids)
        self.invalidate()

    # ---------- список ----------
    def invalidate(self):
        with self._lock:
            self._cache = None

    def list(self, refresh: bool = False) -> dict:
        with self._lock:
            cached = self._cache[1] if (not refresh and self._cache and time.time() - self._cache[0] < LIST_TTL) else None
        if cached is None:
            cached = self._load()
            with self._lock:
                self._cache = (time.time(), cached)
        # «Ваша цена» могла уточниться после загрузки списка — пересчитываем
        for g in cached["games"]:
            for s in g["subcategories"]:
                for l in s["lots"]:
                    l.update(self._my_price_info(l["id"], s["id"], l["price"]))
        return cached

    def _load(self) -> dict:
        acc = self._acc()
        sub_ids = self._known_subcategories()
        games: dict[int, dict] = {}
        errors = []
        still_used = set()
        with self._funpay_lock:
            for sub_id in sorted(sub_ids):
                try:
                    lots = acc.get_my_subcategory_lots(sub_id)
                except Exception as e:
                    logger.debug("TRACEBACK", exc_info=True)
                    errors.append(f"подкатегория {sub_id}: {e.__class__.__name__}")
                    continue
                if not lots:
                    continue
                still_used.add(sub_id)
                sub = lots[0].subcategory
                cat = sub.category
                for l in lots:
                    self._list_price[int(l.id)] = (int(sub.id), l.price)
                game = games.setdefault(cat.id, {"id": cat.id, "name": cat.name, "position": getattr(cat, "position", 0),
                                                  "subcategories": []})
                game["subcategories"].append({
                    "id": sub.id, "name": sub.name,
                    "lots": [{
                        "id": l.id,
                        "title": l.description or "Без названия",
                        "server": l.server, "side": l.side,
                        "price": l.price, "currency": str(l.currency),
                        "amount": l.amount, "auto": l.auto, "active": l.active,
                        "link": l.public_link,
                        "edit_link": f"https://funpay.com/lots/offerEdit?offer={l.id}",
                    } for l in lots],
                })
        if still_used and not self.demo:
            self._remember_subcategories(sub_ids)
        result = sorted(games.values(), key=lambda g: g["name"].lower())
        for g in result:
            g["subcategories"].sort(key=lambda s: s["name"].lower())
            all_lots = [l for s in g["subcategories"] for l in s["lots"]]
            g["total"] = len(all_lots)
            g["active"] = sum(1 for l in all_lots if l["active"])
        return {"games": result, "errors": errors, "updated": int(time.time()), "demo": self.demo}

    def _my_price_info(self, lot_id: int, sub_id: int, list_price: float) -> dict:
        if lot_id in self._my_price:
            return {"my_price": self._my_price[lot_id], "my_price_exact": True}
        coef = self._coef.get(sub_id)
        if coef:
            return {"my_price": round(list_price / coef, 2), "my_price_exact": False}
        return {"my_price": None, "my_price_exact": False}

    def find(self, lot_id: int) -> dict | None:
        for g in self.list()["games"]:
            for s in g["subcategories"]:
                for l in s["lots"]:
                    if l["id"] == lot_id:
                        return {**l, "game": g["name"], "subcategory": s["name"]}
        return None

    # ---------- один лот ----------
    def details(self, lot_id: int) -> dict:
        with self._funpay_lock:
            lf = self._acc().get_lot_fields(lot_id)
        self._remember_fields(lot_id, lf.price)
        methods = []
        if lf.calc_result:
            methods = [{"name": m.name, "price": m.price, "currency": str(m.currency)} for m in lf.calc_result.methods]
        return {
            "id": lot_id, "title": lf.title_ru or lf.title_en, "price": lf.price, "currency": str(lf.currency),
            "active": lf.active, "amount": lf.amount, "buyer_prices": methods,
            "subcategory": lf.subcategory.name if lf.subcategory else None,
            "game": lf.subcategory.category.name if lf.subcategory else None,
        }

    def _apply(self, lot_id: int, *, price: float | None = None, active: bool | None = None,
               price_fn=None) -> tuple[float | None, float | None, bool]:
        """Меняет один лот. Возвращает (старая цена, новая цена, активен)."""
        acc = self._acc()
        last_error = None
        for attempt in range(3):
            try:
                lf = acc.get_lot_fields(lot_id)
                old = lf.price
                self._remember_fields(lot_id, old)
                changed = False
                if price_fn is not None:
                    price = price_fn(old)
                if price is not None and (old is None or abs(price - old) > 1e-9):
                    lf.price = price
                    changed = True
                if active is not None and lf.active != active:
                    lf.active = active
                    changed = True
                if changed:
                    acc.save_lot(lf)
                if lf.price is not None:
                    self._my_price[lot_id] = lf.price
                return old, lf.price, lf.active
            except LotsError:
                raise
            except Exception as e:
                last_error = e
                logger.debug("TRACEBACK", exc_info=True)
                if e.__class__.__name__ in ("LotParsingError", "LotSavingError"):
                    break
                time.sleep(1.5)
        raise LotsError(_error_text(last_error))

    def update_one(self, lot_id: int, price: float | None = None, active: bool | None = None) -> dict:
        if price is not None:
            validate_price(price)
        with self._funpay_lock:
            old, new, act = self._apply(lot_id, price=price, active=active)
        self.invalidate()
        return {"id": lot_id, "old_price": old, "price": new, "active": act}

    # ---------- копия лота ----------
    def copy_info(self, lot_id: int) -> dict:
        """Что можно поменять в копии: название и цена."""
        with self._funpay_lock:
            lf = self._acc().get_lot_fields(lot_id)
        return {"id": lot_id, "title": lf.title_ru or "", "has_title": "fields[summary][ru]" in lf.fields,
                "price": lf.price, "auto_delivery": bool(lf.auto_delivery), "secrets": len(lf.secrets)}

    def copy(self, lot_id: int, title: str | None = None, price: float | None = None, active: bool = False) -> dict:
        """Создаёт новый лот с теми же полями. Товары встроенной автовыдачи FunPay не копируются —
        иначе один и тот же товар продавался бы дважды."""
        from FunPayAPI.types import LotFields
        if price is not None:
            validate_price(price)
        acc = self._acc()
        with self._funpay_lock:
            try:
                lf = acc.get_lot_fields(lot_id)
            except Exception as e:
                logger.debug("TRACEBACK", exc_info=True)
                raise LotsError(_error_text(e))
            fields = dict(lf.fields)
            for k in ("offer_id", "deleted"):
                fields.pop(k, None)
            new = LotFields(0, fields, lf.subcategory, lf.currency, lf.calc_result)
            new.secrets = []
            if lf.auto_delivery:
                new.amount = 0  # товары встроенной автовыдачи остались у старого лота
            if title is not None and "fields[summary][ru]" in fields:
                title = " ".join(str(title).split())
                if not title:
                    raise LotsError("Название не может быть пустым.")
                new.title_ru = title[:250]
            if price is not None:
                new.price = price
            new.active = bool(active)
            try:
                acc.save_lot(new)
            except Exception as e:
                logger.debug("TRACEBACK", exc_info=True)
                raise LotsError(_error_text(e))
        self.invalidate()
        return {"ok": True, "active": bool(active)}

    # ---------- массовые изменения ----------
    def start_bulk(self, lot_ids: list[int], op: dict, user_id: int) -> str:
        if not lot_ids:
            raise LotsError("Не выбрано ни одного лота.")
        if len(lot_ids) > MAX_BULK:
            raise LotsError(f"За раз можно изменить не больше {MAX_BULK} лотов.")
        if any(j["status"] == "running" for j in self.jobs.values()):
            raise LotsError("Уже идёт другое массовое изменение — дождитесь его окончания.")
        price_fn, active = build_operation(op)
        job_id = secrets.token_hex(8)
        job = {"id": job_id, "status": "running", "total": len(lot_ids), "done": 0, "ok": 0, "failed": 0,
               "results": [], "started": int(time.time()), "op": op}
        self.jobs[job_id] = job
        threading.Thread(target=self._run_bulk, args=(job, lot_ids, price_fn, active, user_id),
                         daemon=True, name=f"lots-bulk-{job_id}").start()
        return job_id

    def _run_bulk(self, job: dict, lot_ids: list[int], price_fn, active, user_id: int):
        logger.info(f"Mini App: {user_id} запустил массовое изменение {len(lot_ids)} лотов ({job['op']}).")
        with self._funpay_lock:
            for lot_id in lot_ids:
                item = {"id": lot_id}
                try:
                    old, new, act = self._apply(lot_id, price_fn=price_fn, active=active)
                    item.update(ok=True, old_price=old, price=new, active=act)
                    job["ok"] += 1
                except Exception as e:
                    item.update(ok=False, error=str(e))
                    job["failed"] += 1
                job["results"].append(item)
                job["done"] += 1
                time.sleep(REQUEST_PAUSE)
        job["status"] = "finished"
        job["finished"] = int(time.time())
        self.invalidate()
        logger.info(f"Mini App: массовое изменение завершено: успешно {job['ok']}, с ошибкой {job['failed']}.")
        # чистим старые задачи
        for k in [k for k, j in self.jobs.items() if j["status"] == "finished" and time.time() - j.get("finished", 0) > 3600]:
            self.jobs.pop(k, None)


def validate_price(price: float):
    if not isinstance(price, (int, float)) or math.isnan(price) or math.isinf(price):
        raise LotsError("Некорректная цена.")
    if price <= 0:
        raise LotsError("Цена должна быть больше нуля.")
    if price > 10_000_000:
        raise LotsError("Слишком большая цена.")


def _round(value: float, mode: str) -> float:
    if mode == "int":
        return float(max(1, round(value)))
    if mode == "9":       # «красивые» цены, заканчиваются на 9: 152 -> 159, 1000 -> 1009
        v = max(1, math.ceil(value))
        return float(v - v % 10 + 9 if v >= 10 else v)
    return round(value, 2)


def build_operation(op: dict):
    """
    op = {"kind": "set"|"percent"|"add"|"activate"|"deactivate", "value": число, "round": "2"|"int"|"9"}
    Возвращает (функция новой цены или None, active или None).
    """
    kind = op.get("kind")
    rounding = op.get("round") or "2"
    if kind == "activate":
        return None, True
    if kind == "deactivate":
        return None, False
    try:
        value = float(str(op.get("value")).replace(",", "."))
    except (TypeError, ValueError):
        raise LotsError("Укажите число.")
    if math.isnan(value) or math.isinf(value):
        raise LotsError("Укажите число.")

    if kind == "set":
        validate_price(value)
        new = _round(value, rounding)
        return (lambda old: new), None
    if kind == "percent":
        if value <= -95 or value > 1000:
            raise LotsError("Процент должен быть от −95 до 1000.")

        def fn(old):
            if old is None:
                raise LotsError("У лота нет цены.")
            new = _round(old * (1 + value / 100), rounding)
            validate_price(new)
            return new
        return fn, None
    if kind == "add":
        def fn(old):
            if old is None:
                raise LotsError("У лота нет цены.")
            new = _round(old + value, rounding)
            validate_price(new)
            return new
        return fn, None
    raise LotsError("Неизвестная операция.")


def _error_text(e: Exception | None) -> str:
    if e is None:
        return "Неизвестная ошибка"
    name = e.__class__.__name__
    if name == "LotParsingError":
        return "Лот не найден на FunPay"
    if name == "LotSavingError":
        errors = getattr(e, "errors", None) or {}
        msg = getattr(e, "error_message", None) or ""
        details = "; ".join(f"{v}" for v in errors.values()) if isinstance(errors, dict) else ""
        return f"FunPay не принял изменения{': ' + (details or msg) if (details or msg) else ''}"
    return f"Ошибка связи с FunPay ({name})"
