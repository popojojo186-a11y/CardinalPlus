"""
Демо-режим вкладки «Лоты»: выдуманные лоты, чтобы попробовать интерфейс без реальных лотов на FunPay.

DemoAccount повторяет нужные методы FunPayAPI.Account (get_my_subcategory_lots, get_lot_fields,
save_lot, get_subcategory), но ничего никуда не отправляет. Изменения живут до перезапуска Cardinal.
"""
from __future__ import annotations

import threading
import time

from FunPayAPI.common.enums import Currency, SubCategoryTypes
from FunPayAPI.types import Category, LotFields, MyLotShortcut, PaymentMethod, CalcResult, SubCategory

COMMISSION = 1.1   # покупатель видит цену примерно на 10% выше
DELAY = 0.25       # имитация задержки FunPay

_CATS = {9001: "Steam", 9002: "Brawl Stars", 9003: "Genshin Impact", 9004: "Roblox"}
_SUBS = {
    90011: (9001, "Ключи"), 90012: (9001, "Аккаунты"),
    90021: (9002, "Гемы"), 90022: (9002, "Brawl Pass"),
    90031: (9003, "Аккаунты"),
    90041: (9004, "Робуксы"),
}
_LOTS = [
    (90011, "Cyberpunk 2077 — ключ Steam, Global", 349, 12, True),
    (90011, "Elden Ring — ключ Steam, РФ и СНГ", 1890, 3, True),
    (90011, "Hades II — ключ Steam", 720, 0, False),
    (90011, "Baldur's Gate 3 — ключ Steam", 2190, 5, True),
    (90012, "Аккаунт Steam с 50 играми, полный доступ", 1290, 1, True),
    (90012, "Аккаунт Steam 10 лет, значки, 120 игр", 4990, 1, False),
    (90021, "170 гемов — быстро, вход через Supercell ID", 899, None, True),
    (90021, "360 гемов", 1690, None, True),
    (90021, "950 гемов — выгодно", 3990, None, True),
    (90022, "Brawl Pass на сезон", 649, None, False),
    (90031, "Аккаунт AR55, 5 персонажей 5★", 2400, 1, True),
    (90031, "Стартовый аккаунт AR30 + Рейден", 590, 4, True),
    (90041, "800 Robux — через геймпасс", 690, None, True),
    (90041, "1700 Robux", 1390, None, True),
    (90041, "4500 Robux — для крупных покупок", 3490, None, False),
]


class DemoAccount:
    def __init__(self):
        self._lock = threading.Lock()
        self.categories = {cid: Category(cid, name) for cid, name in _CATS.items()}
        self.subcategories = {sid: SubCategory(sid, name, SubCategoryTypes.COMMON, self.categories[cid])
                              for sid, (cid, name) in _SUBS.items()}
        self.lots: dict[int, dict] = {}
        for i, (sub, title, price, amount, active) in enumerate(_LOTS, start=1):
            self.lots[990000 + i] = {"sub": sub, "title": title, "price": float(price), "amount": amount, "active": active}

    def subcategory_ids(self) -> set[int]:
        return set(self.subcategories)

    def get_subcategory(self, type_, sub_id):
        return self.subcategories.get(int(sub_id))

    def get_my_subcategory_lots(self, sub_id: int, locale=None):
        time.sleep(DELAY / 2)
        sub = self.subcategories[int(sub_id)]
        with self._lock:
            return [MyLotShortcut(lot_id, None, None, l["title"], l["amount"], round(l["price"] * COMMISSION, 2),
                                  Currency.RUB, sub, False, l["active"], "")
                    for lot_id, l in self.lots.items() if l["sub"] == int(sub_id)]

    def get_lot_fields(self, lot_id: int = 0, node_id=None):
        time.sleep(DELAY)
        with self._lock:
            l = dict(self.lots[int(lot_id)])
        sub = self.subcategories[l["sub"]]
        fields = {"price": str(l["price"]), "active": "on" if l["active"] else "", "fields[summary][ru]": l["title"]}
        if l["amount"] is not None:
            fields["amount"] = str(l["amount"])
        methods = [PaymentMethod("Банковская карта", round(l["price"] * COMMISSION, 2), Currency.RUB, 0),
                   PaymentMethod("СБП", round(l["price"] * (COMMISSION - 0.02), 2), Currency.RUB, 1)]
        calc = CalcResult(SubCategoryTypes.COMMON, sub.id, methods, l["price"], None, Currency.UNKNOWN, Currency.RUB)
        return LotFields(int(lot_id), fields, sub, Currency.RUB, calc, None)

    def save_lot(self, lot_fields, locale=None):
        time.sleep(DELAY)
        with self._lock:
            if not lot_fields.lot_id:  # новый лот (копия)
                sub = lot_fields.subcategory.id if lot_fields.subcategory else next(iter(self.subcategories))
                new_id = max(self.lots) + 1
                self.lots[new_id] = {"sub": int(sub), "title": lot_fields.title_ru or "Новый лот",
                                     "price": float(lot_fields.price or 1), "amount": None, "active": bool(lot_fields.active)}
                return
            l = self.lots[int(lot_fields.lot_id)]
            if lot_fields.price is not None:
                l["price"] = float(lot_fields.price)
            l["active"] = bool(lot_fields.active)
