"""
Cardinal Plus: защита от плагинов, которые мешают друг другу в Telegram-боте.

В обычном Cardinal хэндлеры всех плагинов складываются в один общий список, и Telegram-сообщение
достаётся первому подошедшему. Отсюда две проблемы, когда стоят плагины от разных авторов:

1. Одинаковые команды. Если у двух плагинов есть команда /stats, всегда срабатывает тот, что загрузился
   раньше, а второй не срабатывает никогда. Здесь бот вместо этого спрашивает, какой плагин открыть.

2. Ошибка в фильтре одного плагина. Если фильтр (func=...) падает с исключением, сообщение теряется и не
   доходит до плагинов, загруженных позже. Здесь такой фильтр считается «не подошёл», остальные работают.

Подключается в Cardinal.__init_telegram() до регистрации встроенных команд.
"""
from __future__ import annotations

import functools
import html
import logging
import secrets
import threading
import time
from typing import TYPE_CHECKING, Callable

from telebot import util as tb_util
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

if TYPE_CHECKING:
    from cardinal import Cardinal

logger = logging.getLogger("FPC.command_guard")

CB_PREFIX = "cpcmd"
PENDING_TTL = 600  # сколько секунд живёт вопрос «какой плагин открыть»
CORE = None        # владелец встроенных команд Cardinal


class _Entry:
    __slots__ = ("owner", "handler", "func")

    def __init__(self, owner: str | None, handler: Callable, func: Callable | None):
        self.owner = owner
        self.handler = handler
        self.func = func


_lock = threading.RLock()
_cardinal: Cardinal | None = None
_registry: dict[str, list[_Entry]] = {}                       # команда -> кто её зарегистрировал
_pending: dict[str, tuple[float, Message, list[_Entry]]] = {}  # токен -> (время, сообщение, варианты)
_filter_errors: dict[str | None, str] = {}                     # владелец -> текст первой ошибки фильтра


def _owner_of(handler: Callable) -> str | None:
    """UUID плагина, которому принадлежит хэндлер (по глобальной переменной UUID его модуля)."""
    target = handler.func if isinstance(handler, functools.partial) else handler
    g = getattr(target, "__globals__", None)
    if g is None:
        g = getattr(getattr(target, "__call__", None), "__globals__", None)
    uuid = g.get("UUID") if isinstance(g, dict) else None
    if isinstance(uuid, str) and _cardinal is not None and uuid in _cardinal.plugins:
        return uuid
    return CORE


def owner_name(owner: str | None) -> str:
    if owner is CORE:
        return "Cardinal"
    plugin = _cardinal.plugins.get(owner) if _cardinal else None
    return plugin.name if plugin else "Неизвестный плагин"


def _active(owner: str | None) -> bool:
    if owner is CORE:
        return True
    plugin = _cardinal.plugins.get(owner) if _cardinal else None
    return bool(plugin and plugin.enabled)


def _safe_filter(func: Callable, owner: str | None) -> Callable:
    """Фильтр, который при ошибке отвечает «не подошло», а не роняет обработку сообщения."""

    def safe(obj):
        try:
            return func(obj)
        except Exception as e:
            if owner not in _filter_errors:
                _filter_errors[owner] = f"{type(e).__name__}: {e}"
                logger.warning(f"{owner_name(owner)}: ошибка в фильтре Telegram-хэндлера ({type(e).__name__}: {e}). "
                               f"Этот обработчик пропускается, остальные плагины работают.")
            logger.debug("TRACEBACK", exc_info=True)
            return False

    return safe


def _candidates(command: str, message: Message) -> list[_Entry]:
    """Включённые владельцы команды, по одному хэндлеру на каждого."""
    result, seen = [], set()
    with _lock:
        entries = list(_registry.get(command, []))
    for e in entries:
        if e.owner in seen or not _active(e.owner):
            continue
        if e.func is not None and not e.func(message):
            continue
        seen.add(e.owner)
        result.append(e)
    return result


def _run(entry: _Entry, message: Message) -> None:
    try:
        entry.handler(message)
    except Exception:
        logger.error(f"{owner_name(entry.owner)}: ошибка при выполнении команды.")
        logger.debug("TRACEBACK", exc_info=True)


def _ask(command: str, message: Message, options: list[_Entry]) -> None:
    token = secrets.token_hex(6)
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v[0] > PENDING_TTL]:
            _pending.pop(k, None)
        _pending[token] = (now, message, options)
    kb = InlineKeyboardMarkup()
    for i, e in enumerate(options):
        label = "🐦 Cardinal (встроенная команда)" if e.owner is CORE else f"🧩 {owner_name(e.owner)}"
        kb.add(InlineKeyboardButton(label[:60], callback_data=f"{CB_PREFIX}:{token}:{i}"))
    kb.add(InlineKeyboardButton("✖️ Отмена", callback_data=f"{CB_PREFIX}:{token}:x"))
    _cardinal.telegram.bot.send_message(
        message.chat.id,
        f"Команда <code>/{html.escape(command)}</code> есть сразу у нескольких плагинов. Какой открыть?",
        reply_markup=kb, parse_mode="HTML")


def _dispatch(entry: _Entry, message: Message) -> None:
    command = tb_util.extract_command(message.text or "")
    options = _candidates(command, message) if command else []
    if len(options) > 1:
        _ask(command, message, options)
    elif len(options) == 1:
        _run(options[0], message)
    else:
        _run(entry, message)


def _on_choice(call: CallbackQuery) -> None:
    tg = _cardinal.telegram
    bot = tg.bot
    if call.from_user.id not in tg.authorized_users:
        return
    try:
        _, token, choice = call.data.split(":")
    except ValueError:
        return
    with _lock:
        item = _pending.pop(token, None)
    try:
        bot.delete_message(call.message.chat.id, call.message.id)
    except Exception:
        pass
    if choice == "x":
        bot.answer_callback_query(call.id)
        return
    if not item or time.time() - item[0] > PENDING_TTL or not choice.isdigit() or int(choice) >= len(item[2]):
        bot.answer_callback_query(call.id, "Кнопка устарела. Отправьте команду ещё раз.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _run(item[2][int(choice)], item[1])


def install(cardinal: Cardinal) -> None:
    """Подменяет TGBot.msg_handler / cbq_handler на защищённые версии. Вызывать до TGBot.init()."""
    global _cardinal
    tg = cardinal.telegram
    if tg is None or getattr(tg, "_command_guard", False):
        return
    _cardinal = cardinal
    tg._command_guard = True
    orig_msg, orig_cbq = tg.msg_handler, tg.cbq_handler

    def msg_handler(handler, **kwargs):
        owner = _owner_of(handler)
        if kwargs.get("func") is not None:
            kwargs["func"] = _safe_filter(kwargs["func"], owner)
        commands = kwargs.get("commands")
        if not commands:
            return orig_msg(handler, **kwargs)

        entry = _Entry(owner, handler, kwargs.get("func"))
        with _lock:
            for command in commands:
                entries = _registry.setdefault(command, [])
                others = {e.owner for e in entries} - {owner}
                if others and owner not in {e.owner for e in entries}:
                    names = ", ".join(f"«{owner_name(o)}»" for o in [*others, owner])
                    logger.warning(f"Команда /{command} есть сразу у {names}. "
                                   f"Бот будет спрашивать, какой плагин открыть.")
                entries.append(entry)
        return orig_msg(lambda message: _dispatch(entry, message), **kwargs)

    def cbq_handler(handler, func, **kwargs):
        return orig_cbq(handler, _safe_filter(func, _owner_of(handler)), **kwargs)

    tg.msg_handler = msg_handler
    tg.cbq_handler = cbq_handler
    orig_cbq(_on_choice, lambda c: bool(c.data) and c.data.startswith(f"{CB_PREFIX}:"))


def conflicts() -> dict[str, list[str | None]]:
    """Команды, которые сейчас есть сразу у нескольких включённых владельцев."""
    result = {}
    with _lock:
        items = [(cmd, list(entries)) for cmd, entries in _registry.items()]
    for command, entries in items:
        owners = []
        for e in entries:
            if e.owner not in owners and _active(e.owner):
                owners.append(e.owner)
        if len(owners) > 1:
            result[command] = owners
    return result


def plugin_warnings(uuid: str) -> list[str]:
    """Готовые фразы для карточки плагина в приложении."""
    result = []
    for command, owners in sorted(conflicts().items()):
        if uuid in owners:
            others = ", ".join("Cardinal" if o is CORE else f"«{owner_name(o)}»" for o in owners if o != uuid)
            result.append(f"Команда /{command} есть ещё у: {others}. Когда отправите её боту, он спросит, какой плагин открыть.")
    if uuid in _filter_errors:
        result.append(f"В плагине ошибка в обработчике сообщений бота ({_filter_errors[uuid]}). "
                      f"Часть его функций в боте может не работать. Остальным плагинам это не мешает.")
    return result
