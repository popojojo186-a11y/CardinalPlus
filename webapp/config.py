"""
Настройки Mini App. Хранятся отдельно от _main.cfg, чтобы не ломать совместимость с оригинальным Cardinal.
"""
from __future__ import annotations

import json
import os

CONFIG_PATH = "configs/webapp.json"

DEFAULTS = {
    "enabled": True,
    "host": "127.0.0.1",
    "port": 8095,
    # "cloudflare" — автоматический туннель (по умолчанию), "none" — без туннеля (если указан public_url).
    "tunnel": "cloudflare",
    # Свой адрес (https://my.domain.com). Если указан, туннель не запускается.
    "public_url": "",
    "menu_button_text": "Cardinal+",
}


def load() -> dict:
    data = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except (OSError, ValueError):
            pass
    else:
        save(data)
    return data


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
