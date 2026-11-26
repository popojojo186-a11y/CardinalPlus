"""
История продаж для статистики и отчёта за день.

FunPay отдаёт заказы страницами (примерно по 100 штук), поэтому длинные периоды загружаются
в фоне постранично, с паузой между запросами, и кэшируются на несколько минут.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.webapp")

PAGE_LIMIT = 60      # не больше 60 страниц (~6000 заказов) за одну загрузку
PAGE_PAUSE = 0.7     # сек между страницами, чтобы FunPay не ограничил запросы
CACHE_TTL = 300      # сек: столько живёт загруженная история
REFUND = ("refunded", "partially_refunded")


def _date(o: dict) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(o["date"]) if o.get("date") else None
    except (TypeError, ValueError):
        return None


class SalesHistory:
    def __init__(self, cardinal: Cardinal, to_dict: Callable):
        self.c = cardinal
        self.to_dict = to_dict
        self._lock = threading.Lock()
        self._orders: list[dict] = []
        self._covered: datetime.datetime | None = None  # все заказы новее этой даты загружены
        self._complete = False                          # дошли до самого первого заказа
        self._fetched = 0.0
        self._job: dict | None = None

    # ---------- загрузка ----------
    def _fetch(self, since: datetime.datetime, job: dict | None = None) -> None:
        orders, start, pages, complete = [], None, 0, False
        oldest = None
        while pages < PAGE_LIMIT:
            next_id, items, *_ = self.c.account.get_sales(start_from=start)
            pages += 1
            if job is not None:
                job["pages"] = pages
            orders.extend(self.to_dict(o) for o in items)
            dates = [d for d in (_date(o) for o in orders[-len(items):]) if d] if items else []
            if dates:
                oldest = min(dates) if oldest is None else min(oldest, min(dates))
            if not next_id or not items:
                complete = True
                break
            if oldest is not None and oldest < since:
                break
            start = next_id
            time.sleep(PAGE_PAUSE)
        with self._lock:
            self._orders = orders
            self._complete = complete
            self._covered = since if (complete or (oldest is not None and oldest < since)) else oldest
            self._fetched = time.time()

    def _fresh_for(self, since: datetime.datetime) -> bool:
        with self._lock:
            if time.time() - self._fetched > CACHE_TTL or self._covered is None and not self._complete:
                return False
            return self._complete or (self._covered is not None and self._covered <= since)

    def _orders_since(self, since: datetime.datetime) -> list[dict]:
        with self._lock:
            return [o for o in self._orders if (d := _date(o)) is not None and d >= since]

    def request(self, days: int, refresh: bool = False) -> dict:
        """Для статистики: либо готовые заказы, либо «загружаю, страниц: N» (загрузка идёт в фоне)."""
        since = datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=days - 1), datetime.time())
        if not refresh and self._fresh_for(since):
            with self._lock:
                partial = not self._complete and self._covered is not None and self._covered > since
                covered = self._covered
            return {"ready": True, "orders": self._orders_since(since), "since": since.isoformat(),
                    "partial": partial, "covered_from": covered.isoformat() if partial and covered else None}
        with self._lock:
            job = self._job
            failed_recently = job is not None and job.get("error") and time.time() - job.get("ended", 0) < 30
            if failed_recently and not refresh:
                return {"ready": False, "error": job["error"]}
            if job is None or not job["running"] and (refresh or not self._fresh_for_unlocked(since)) or \
                    job["running"] and job["since"] > since:
                job = self._job = {"since": since, "pages": 0, "running": True, "error": None}
                threading.Thread(target=self._run_job, args=(job,), daemon=True, name="webapp-sales").start()
        return {"ready": False, "pages": job["pages"]}

    def _fresh_for_unlocked(self, since: datetime.datetime) -> bool:
        if time.time() - self._fetched > CACHE_TTL:
            return False
        return self._complete or (self._covered is not None and self._covered <= since)

    def _run_job(self, job: dict) -> None:
        try:
            self._fetch(job["since"], job)
        except Exception as e:
            logger.debug("TRACEBACK", exc_info=True)
            job["error"] = "Не удалось загрузить заказы с FunPay. Попробуйте через минуту."
            logger.warning(f"Mini App: статистика — ошибка загрузки заказов: {e}")
        finally:
            job["ended"] = time.time()
            job["running"] = False

    def today(self) -> list[dict]:
        """Для отчёта: заказы за сегодня (обычно это 1–2 страницы), загружаются сразу."""
        since = datetime.datetime.combine(datetime.date.today(), datetime.time())
        if not self._fresh_for(since):
            self._fetch(since)
        return self._orders_since(since)


# ---------- подсчёт ----------
def summarize(orders: list[dict], days: int) -> dict:
    """Сводка за период: выручка, средний чек, возвраты, по дням, по часам, лучшие товары и покупатели."""
    today = datetime.date.today()
    day_keys = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    by_day = {k: {"date": k, "count": 0, "sum": defaultdict(float)} for k in day_keys}
    by_hour = [0] * 24
    revenue: dict[str, float] = defaultdict(float)
    lots: dict[str, dict] = {}
    buyers: dict[str, dict] = {}
    refunds = paid = closed = items = 0

    for o in orders:
        d = _date(o)
        status = o.get("status")
        cur = str(o.get("currency") or "")
        price = float(o.get("price") or 0)
        lot = lots.setdefault(o.get("description") or "—", {"title": o.get("description") or "—", "count": 0,
                                                             "refunds": 0, "sum": defaultdict(float)})
        b = buyers.setdefault(o.get("buyer") or "—", {"name": o.get("buyer") or "—", "id": o.get("buyer_id"), "count": 0,
                                                     "sum": defaultdict(float), "last": None})
        if status in REFUND:
            refunds += 1
            lot["refunds"] += 1
            continue
        paid += status == "paid"
        closed += status == "closed"
        items += int(o.get("amount") or 1)
        revenue[cur] += price
        lot["count"] += 1
        lot["sum"][cur] += price
        b["count"] += 1
        b["sum"][cur] += price
        if d:
            b["last"] = max(b["last"] or d.isoformat(), d.isoformat())
            if (k := d.date().isoformat()) in by_day:
                by_day[k]["count"] += 1
                by_day[k]["sum"][cur] += price
            by_hour[d.hour] += 1

    main = max(revenue, key=revenue.get) if revenue else ""
    sold = paid + closed
    active_buyers = [b for b in buyers.values() if b["count"]]
    repeat = sum(1 for b in active_buyers if b["count"] >= 2)

    def money(m: dict) -> dict:
        return {k: round(v, 2) for k, v in m.items() if v}

    top_lots = sorted((l for l in lots.values() if l["count"] or l["refunds"]),
                      key=lambda l: (-l["sum"].get(main, 0), -l["count"]))[:15]
    top_buyers = sorted(active_buyers, key=lambda b: (-b["sum"].get(main, 0), -b["count"]))[:15]
    return {
        "days": days,
        "currency": main,
        "revenue": money(revenue),
        "orders": sold,
        "paid": paid,
        "closed": closed,
        "refunds": refunds,
        "refund_rate": round(refunds / (sold + refunds) * 100, 1) if sold + refunds else 0,
        "items": items,
        "avg": round(revenue.get(main, 0) / sold, 2) if sold else 0,
        "buyers": len(active_buyers),
        "repeat_buyers": repeat,
        "repeat_rate": round(repeat / len(active_buyers) * 100, 1) if active_buyers else 0,
        "by_day": [{"date": v["date"], "count": v["count"], "sum": money(v["sum"])} for v in by_day.values()],
        "by_hour": by_hour,
        "top_lots": [{"title": l["title"], "count": l["count"], "refunds": l["refunds"], "sum": money(l["sum"])} for l in top_lots],
        "top_buyers": [{"name": b["name"], "id": b["id"], "count": b["count"], "sum": money(b["sum"]), "last": b["last"]} for b in top_buyers],
        "statuses": dict(Counter(o.get("status") for o in orders)),
    }
