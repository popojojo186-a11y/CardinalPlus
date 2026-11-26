"""
Расписание лотов: включать и выключать выбранные лоты по времени.

Правило: «лоты A, B, C работают с 08:00 до 23:00 по будням». Внутри окна лоты включены,
вне окна — выключены. Окно может переходить через полночь (20:00–02:00).
Лоты меняются только в момент перехода (утром включились, вечером выключились) — если вы вручную
включите лот ночью, расписание не будет выключать его каждую минуту.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import secrets
import threading
import time

from webapp.guard import _clock

logger = logging.getLogger("FPC.webapp")

PATH = os.path.join("storage", "cache", "webapp_lot_schedule.json")
LOOP = 30           # сек между проверками
APPLY_PAUSE = 1.0   # сек между лотами (FunPay не любит частые изменения)
MAX_RULES = 30
MAX_LOTS = 200
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def rule_wants_on(rule: dict, now: datetime.datetime) -> bool:
    """Должны ли лоты правила быть включены сейчас."""
    s, e = _clock(rule.get("on"), (8, 0)), _clock(rule.get("off"), (23, 0))
    days = set(rule.get("days") or range(7))
    t = (now.hour, now.minute)
    if s == e:
        return now.weekday() in days
    if s < e:
        return now.weekday() in days and s <= t < e
    # через полночь: вечер — сегодняшний день правила, ночь до e — вчерашний
    if t >= s:
        return now.weekday() in days
    if t < e:
        return (now - datetime.timedelta(days=1)).weekday() in days
    return False


class Schedule:
    def __init__(self, lots_service, audit=None):
        self.lots = lots_service
        self.audit = audit
        self._lock = threading.RLock()
        data = self._load()
        self.rules: list[dict] = [r for r in data.get("rules") or [] if isinstance(r, dict) and r.get("id")]
        self.applied: dict[str, str] = dict(data.get("applied") or {})
        self.log: list[dict] = list(data.get("log") or [])[-50:]
        self._busy = threading.Lock()
        self._started = False

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
            data = {"rules": self.rules, "applied": self.applied, "log": self.log[-50:]}
            try:
                os.makedirs(os.path.dirname(PATH), exist_ok=True)
                tmp = PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, PATH)
            except OSError:
                logger.debug("TRACEBACK", exc_info=True)

    # ---------- правила ----------
    def state(self) -> dict:
        now = datetime.datetime.now()
        with self._lock:
            rules = [{**r, "now_on": rule_wants_on(r, now), "applied": self.applied.get(r["id"])} for r in self.rules]
            return {"rules": rules, "log": list(reversed(self.log[-20:])), "busy": self._busy.locked()}

    def save_rule(self, data: dict) -> dict:
        name = " ".join(str(data.get("name") or "").split())[:60] or "Расписание"
        on, off = str(data.get("on") or ""), str(data.get("off") or "")
        for v in (on, off):
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", v):
                raise ValueError("Время в формате ЧЧ:ММ, например 08:00.")
        on, off = "%02d:%02d" % _clock(on, (8, 0)), "%02d:%02d" % _clock(off, (23, 0))
        if on == off:
            raise ValueError("Время включения и выключения совпадает.")
        days = sorted({int(d) for d in data.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            raise ValueError("Выберите хотя бы один день.")
        lots = []
        for x in data.get("lots") or []:
            try:
                lots.append(int(x))
            except (TypeError, ValueError):
                continue
        lots = list(dict.fromkeys(lots))
        if not lots:
            raise ValueError("Отметьте хотя бы один лот.")
        if len(lots) > MAX_LOTS:
            raise ValueError(f"Не больше {MAX_LOTS} лотов в одном расписании.")
        titles = {str(k): str(v)[:120] for k, v in (data.get("titles") or {}).items() if str(k).isdigit()}
        with self._lock:
            rid = str(data.get("id") or "")
            old = next((r for r in self.rules if r["id"] == rid), None)
            if old is None:
                if len(self.rules) >= MAX_RULES:
                    raise ValueError(f"Не больше {MAX_RULES} расписаний.")
                rid = secrets.token_hex(4)
            rule = {"id": rid, "name": name, "on": on, "off": off, "days": days, "lots": lots,
                    "titles": {str(l): titles.get(str(l)) or (old or {}).get("titles", {}).get(str(l)) or "" for l in lots},
                    "enabled": bool(data.get("enabled", True))}
            if old is None:
                self.rules.append(rule)
            else:
                self.rules[self.rules.index(old)] = rule
                self.applied.pop(rid, None)  # правило изменилось — применим заново
            self._save()
        threading.Thread(target=self.tick, daemon=True).start()
        return self.state()

    def toggle(self, rid: str, enabled: bool) -> dict:
        with self._lock:
            rule = next((r for r in self.rules if r["id"] == rid), None)
            if rule is None:
                raise ValueError("Расписание не найдено.")
            rule["enabled"] = bool(enabled)
            self.applied.pop(rid, None)
            self._save()
        if enabled:
            threading.Thread(target=self.tick, daemon=True).start()
        return self.state()

    def delete(self, rid: str) -> dict:
        with self._lock:
            self.rules = [r for r in self.rules if r["id"] != rid]
            self.applied.pop(rid, None)
            self._save()
        return self.state()

    # ---------- применение ----------
    def tick(self, now: datetime.datetime | None = None) -> int:
        """Применяет правила, у которых наступил переход. Возвращает, сколько лотов изменено."""
        if not self._busy.acquire(blocking=False):
            return 0
        changed = 0
        try:
            now = now or datetime.datetime.now()
            with self._lock:
                todo = [(r, "on" if rule_wants_on(r, now) else "off") for r in self.rules
                        if r.get("enabled") and self.applied.get(r["id"]) != ("on" if rule_wants_on(r, now) else "off")]
            for rule, want in todo:
                ok, failed = 0, []
                for lot_id in rule["lots"]:
                    try:
                        self.lots.update_one(int(lot_id), active=(want == "on"))
                        ok += 1
                    except Exception as e:
                        failed.append(f"{lot_id}: {e}")
                        logger.debug("TRACEBACK", exc_info=True)
                    time.sleep(APPLY_PAUSE)
                changed += ok
                with self._lock:
                    self.applied[rule["id"]] = want
                    entry = {"t": int(time.time()), "rule": rule["name"], "action": want, "ok": ok, "failed": len(failed)}
                    self.log.append(entry)
                    self._save()
                text = f"Расписание «{rule['name']}»: {'включено' if want == 'on' else 'выключено'} лотов — {ok}" + \
                       (f", не получилось — {len(failed)}" if failed else "")
                logger.info(f"Mini App: {text}")
                if self.audit is not None:
                    self.audit.add(None, "lots", text)
        finally:
            self._busy.release()
        return changed

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        def loop():
            time.sleep(20)
            while True:
                try:
                    self.tick()
                except Exception:
                    logger.debug("TRACEBACK", exc_info=True)
                time.sleep(LOOP)
        threading.Thread(target=loop, daemon=True, name="webapp-schedule").start()
