"""
Деньги и покупатели: себестоимость и чистая прибыль, план продаж на месяц, список покупателей.

Себестоимость задаётся для товара (по названию, как оно приходит в заказах) — сколько стоил вам
1 штуке. Можно задать и общий процент «себестоимость = N% от цены» для товаров без своей цены.
Прибыль = цена заказа − себестоимость × количество (возвраты не считаются).
"""
from __future__ import annotations

import calendar
import datetime
import json
import logging
import os
import threading
from collections import defaultdict

logger = logging.getLogger("FPC.webapp")

PATH = os.path.join("storage", "cache", "webapp_business.json")
REFUND = ("refunded", "partially_refunded")
MAX_COSTS = 2000


def _date(o: dict) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(o["date"]) if o.get("date") else None
    except (TypeError, ValueError):
        return None


class Business:
    def __init__(self):
        self._lock = threading.RLock()
        data = self._load()
        self.costs: dict[str, float] = {str(k): float(v) for k, v in (data.get("costs") or {}).items()
                                        if isinstance(v, (int, float))}
        self.default_pct: float = float(data.get("default_pct") or 0)
        self.plan: float = float(data.get("plan") or 0)

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
            data = {"costs": self.costs, "default_pct": self.default_pct, "plan": self.plan}
            try:
                os.makedirs(os.path.dirname(PATH), exist_ok=True)
                tmp = PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, PATH)
            except OSError:
                logger.debug("TRACEBACK", exc_info=True)

    # ---------- настройки ----------
    @staticmethod
    def _number(value, name: str, high: float) -> float:
        try:
            v = float(str(value).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            raise ValueError(f"{name}: нужно число.")
        if not 0 <= v <= high:
            raise ValueError(f"{name}: от 0 до {high:g}.")
        return round(v, 2)

    def set_cost(self, title: str, value) -> dict:
        title = str(title or "").strip()
        if not title or len(title) > 500:
            raise ValueError("Не указан товар.")
        with self._lock:
            if value is None or str(value).strip() == "":
                self.costs.pop(title, None)
            else:
                if title not in self.costs and len(self.costs) >= MAX_COSTS:
                    raise ValueError("Слишком много товаров с себестоимостью.")
                self.costs[title] = self._number(value, "Себестоимость", 10_000_000)
            self._save()
        return self.settings()

    def set_default_pct(self, value) -> dict:
        with self._lock:
            self.default_pct = self._number(value or 0, "Процент", 100)
            self._save()
        return self.settings()

    def set_plan(self, value) -> dict:
        with self._lock:
            self.plan = self._number(value or 0, "План", 1_000_000_000)
            self._save()
        return self.settings()

    def settings(self) -> dict:
        with self._lock:
            return {"costs": dict(self.costs), "default_pct": self.default_pct, "plan": self.plan}

    def has_costs(self) -> bool:
        return bool(self.costs) or self.default_pct > 0

    # ---------- прибыль ----------
    def cost_of(self, o: dict) -> float | None:
        """Себестоимость заказа или None, если она неизвестна."""
        amount = int(o.get("amount") or 1)
        title = o.get("description") or ""
        if title in self.costs:
            return round(self.costs[title] * amount, 2)
        if self.default_pct > 0:
            return round(float(o.get("price") or 0) * self.default_pct / 100, 2)
        return None

    def profit(self, orders: list[dict], currency: str = "₽") -> dict:
        """Выручка, себестоимость и прибыль по заказам в одной валюте (обычно ₽)."""
        revenue = cost = known_revenue = 0.0
        unknown = 0
        for o in orders:
            if o.get("status") in REFUND or str(o.get("currency") or "") != currency:
                continue
            price = float(o.get("price") or 0)
            revenue += price
            c = self.cost_of(o)
            if c is None:
                unknown += 1
            else:
                cost += c
                known_revenue += price
        profit = known_revenue - cost
        return {"currency": currency, "revenue": round(revenue, 2), "cost": round(cost, 2),
                "profit": round(profit, 2), "known_revenue": round(known_revenue, 2), "unknown": unknown,
                "margin": round(profit / known_revenue * 100, 1) if known_revenue else None}

    def lot_profits(self, orders: list[dict], currency: str = "₽") -> dict[str, dict]:
        out: dict[str, dict] = {}
        for o in orders:
            if o.get("status") in REFUND or str(o.get("currency") or "") != currency:
                continue
            title = o.get("description") or "—"
            r = out.setdefault(title, {"revenue": 0.0, "cost": 0.0, "known": True})
            r["revenue"] += float(o.get("price") or 0)
            c = self.cost_of(o)
            if c is None:
                r["known"] = False
            else:
                r["cost"] += c
        for title, r in out.items():
            r["profit"] = round(r["revenue"] - r["cost"], 2) if r["known"] else None
            r["unit_cost"] = self.costs.get(title)
        return out

    # ---------- план на месяц ----------
    def plan_status(self, orders: list[dict], today: datetime.date | None = None, currency: str = "₽") -> dict:
        today = today or datetime.date.today()
        first = today.replace(day=1)
        days_in = calendar.monthrange(today.year, today.month)[1]
        month = [o for o in orders if (d := _date(o)) and d.date() >= first and d.date() <= today]
        done = sum(float(o.get("price") or 0) for o in month
                   if o.get("status") not in REFUND and str(o.get("currency") or "") == currency)
        elapsed = today.day
        forecast = done / elapsed * days_in if elapsed else 0
        left_days = days_in - today.day + 1  # сегодня ещё можно продать
        target = self.plan
        need = max(0.0, target - done)
        return {"target": target, "done": round(done, 2), "currency": currency,
                "pct": round(done / target * 100, 1) if target else None,
                "forecast": round(forecast, 2), "forecast_pct": round(forecast / target * 100, 1) if target else None,
                "per_day": round(need / left_days, 2) if target and left_days else 0,
                "days_left": left_days, "days_in": days_in, "month": today.month, "year": today.year,
                "profit": self.profit(month, currency) if self.has_costs() else None}

    # ---------- покупатели ----------
    def buyers(self, orders: list[dict], reviews: dict[str, dict] | None = None, blacklist=()) -> list[dict]:
        bl = set(blacklist or [])
        reviews = reviews or {}
        out: dict[str, dict] = {}
        for o in orders:
            name = o.get("buyer") or ""
            if not name:
                continue
            b = out.setdefault(name, {"name": name, "id": o.get("buyer_id"), "orders": 0, "refunds": 0,
                                      "spent": defaultdict(float), "first": None, "last": None, "items": 0,
                                      "titles": defaultdict(int)})
            d = _date(o)
            iso = d.isoformat() if d else None
            if iso:
                b["first"] = min(b["first"] or iso, iso)
                b["last"] = max(b["last"] or iso, iso)
            if o.get("status") in REFUND:
                b["refunds"] += 1
                continue
            b["orders"] += 1
            b["items"] += int(o.get("amount") or 1)
            b["spent"][str(o.get("currency") or "")] += float(o.get("price") or 0)
            b["titles"][o.get("description") or "—"] += 1
        result = []
        for b in out.values():
            fav = max(b["titles"].items(), key=lambda x: x[1])[0] if b["titles"] else None
            rv = reviews.get(b["name"].lower())
            result.append({"name": b["name"], "id": b["id"], "orders": b["orders"], "refunds": b["refunds"],
                           "items": b["items"], "spent": {k: round(v, 2) for k, v in b["spent"].items() if v},
                           "first": b["first"], "last": b["last"], "repeat": b["orders"] >= 2, "favorite": fav,
                           "reviews": rv, "blacklisted": b["name"] in bl})
        result.sort(key=lambda x: (-x["spent"].get("₽", 0), -x["orders"], x["name"].lower()))
        return result
