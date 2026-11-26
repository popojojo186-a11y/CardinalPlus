# Плагины с интерфейсом в Cardinal+

Любой плагин FunPay Cardinal работает в Cardinal+ без изменений: его можно включать и выключать
в приложении, а его настройки, как и раньше, открываются в боте.

Чтобы у плагина появился интерфейс в приложении, добавьте в него словарь `WEBAPP`.
В обычном Cardinal этот словарь просто игнорируется, так что плагин останется совместимым.

## 1. Настройки по схеме (без HTML)

```python
try:
    from webapp.plugin_api import settings
except ImportError:      # обычный Cardinal без Mini App
    settings = None

WEBAPP = {
    "icon": "💌",
    "settings": [
        {"type": "section", "label": "Основное"},
        {"key": "enabled", "type": "toggle",   "label": "Включено", "default": True},
        {"key": "text",    "type": "textarea", "label": "Текст", "default": "Спасибо!", "hint": "$username — ник"},
        {"key": "delay",   "type": "number",   "label": "Задержка", "default": 3, "min": 0, "max": 60},
        {"key": "mode",    "type": "select",   "label": "Режим", "default": "a",
         "options": [["a", "Вариант A"], ["b", "Вариант B"]]},
        {"key": "name",    "type": "text",     "label": "Подпись", "default": ""},
    ],
    # необязательно: вызывается после каждого изменения
    "on_change": lambda cardinal, key, value: None,
}

# Чтение значения в любом месте плагина:
settings(UUID).get("text")
```

Значения хранятся в `storage/webapp_plugins/<UUID>.json`. Приложение само проверяет типы и
ограничения `min`, `max` и `max_length`.

## Настройки в своём конфиге плагина

Если плагин уже хранит настройки в своём файле (например, их меняют и через Telegram-бота),
не нужно заводить второе хранилище. Укажите две функции — приложение будет читать и сохранять через них:

```python
WEBAPP = {
    "settings": [...],                                      # схема полей, как выше
    "values": lambda cardinal: {"enabled": CONFIG["enabled"]},  # текущие значения
    "save": save_setting,                                   # save_setting(cardinal, key, value)
}
```

Если `save` выбрасывает `ValueError("текст")`, приложение покажет этот текст пользователю.

## 2. Своя страница и свои методы

```python
def api_stats(cardinal, data: dict):
    return {"sent": 10}          # всё, что сериализуется в JSON

WEBAPP = {
    "page": "my_plugin.html",    # путь относительно файла плагина, внутри папки plugins
    "routes": {"stats": api_stats},
}
```

Сама страница:

```html
<script src="/static/plugin-sdk.js"></script>
<div class="card" id="out"></div>
<script>
  Plugin.call("stats", {days: 7}).then(r => out.textContent = r.sent);
</script>
```

Через SDK доступны `Plugin.call(name, data)`, `Plugin.toast(text)`, `Plugin.haptic()` и `Plugin.openLink(url)`.
Цвета темы Telegram и классы приложения (`card`, `list`, `item`, `btn`, `grid`, `stat`, `switch`)
подключаются к странице автоматически.

Все запросы проходят проверку подписи Telegram, поэтому вызвать методы плагина может
только авторизованный пользователь Cardinal.

Готовый пример лежит в `webapp/examples/thanks_plugin.py`.

## Страница прямо внутри .py

Чтобы плагин был одним файлом (его можно поставить кнопкой «Установить плагин» в приложении),
HTML страницы можно положить в строку:

```python
WEBAPP = {
    "page_html": """<!doctype html> ... <script src="/static/plugin-sdk.js"></script> ...""",
    "page_title": "Аккаунты",   # заголовок над страницей (по умолчанию «Страница плагина»)
    "page_first": True,         # показать страницу выше настроек
    "routes": {...},
}
```

В методах из `routes` можно выбрасывать `ValueError("текст")` — пользователь увидит этот текст.
На странице доступно `await Plugin.confirm("Удалить?")` — диалог подтверждения приложения.

## Телефон и Панель

`Plugin.layout` — вид приложения: `"mobile"` (телефон) или `"desktop"` (Панель на компьютере).
Тот же вид стоит в `<html data-layout="...">`, так что его можно использовать и в CSS.
Принято так: на телефоне — только основное, в Панели — расширенная версия (статистика, таблицы, массовые действия).

```js
if (Plugin.layout === "desktop") showStats();
```

`Plugin.openChat(chatId, "ник")` открывает переписку с покупателем в разделе «Чаты» приложения
(`chatId` — id чата FunPay, например `event.message.chat_id`). В старых версиях приложения откроется чат на FunPay.
