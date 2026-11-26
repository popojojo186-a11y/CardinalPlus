"""
Cardinal Plus: превращает огромные трейсбеки TeleBot о сетевых сбоях (таймаут, обрыв соединения)
в одну короткую строку. Бот после таких ошибок сам переподключается — это не поломка.
"""
from __future__ import annotations

import logging
import time

NETWORK_MARKERS = ("ReadTimeout", "ConnectTimeout", "ConnectionError", "RemoteDisconnected",
                   "Read timed out", "Max retries exceeded", "ConnectionResetError", "ProxyError", "SSLError")
SHORT_TEXT = "Telegram: нет ответа от api.telegram.org, переподключаюсь... " \
             "(если повторяется часто — включите прокси для Telegram)"
MIN_INTERVAL = 60  # не чаще раза в минуту


class _NetworkErrorFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self._last = 0.0

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:
            return True
        if not any(m in text for m in NETWORK_MARKERS):
            return True
        now = time.time()
        if now - self._last < MIN_INTERVAL:
            return False
        self._last = now
        record.msg = SHORT_TEXT
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.levelno = logging.WARNING
        record.levelname = "WARNING"
        return True


def install() -> None:
    logger = logging.getLogger("TeleBot")
    if not any(isinstance(f, _NetworkErrorFilter) for f in logger.filters):
        logger.addFilter(_NetworkErrorFilter())
