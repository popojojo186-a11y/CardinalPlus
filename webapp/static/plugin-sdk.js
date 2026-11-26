/*
 * SDK для собственных страниц плагинов (WEBAPP["page"]).
 * Подключение: <script src="/static/plugin-sdk.js"></script>
 *
 *   const data = await Plugin.call("stats", {days: 7});   // вызовет WEBAPP["routes"]["stats"](cardinal, {"days": 7})
 *   Plugin.toast("Готово");
 *   if (Plugin.layout === "desktop") { ... }               // Панель на компьютере: можно показать больше
 *   Plugin.openChat(chatId, "ник");                         // открыть переписку в разделе «Чаты»
 *
 * Страница открывается внутри приложения, поэтому стили Telegram (переменные --tg-theme-*)
 * и базовые стили приложения подключаются автоматически.
 */
(() => {
    const parent = window.parent;
    const host = parent && parent.CardinalPlus;
    const uuid = (location.pathname.match(/\/plugin\/([0-9a-fA-F-]{36})\//) || [])[1];

    // Переносим тему (светлая/тёмная) и переменные Telegram из основного окна.
    try { document.documentElement.dataset.theme = parent.document.documentElement.dataset.theme || "light"; } catch (e) {}
    // Вид приложения: "mobile" (телефон — только основное) или "desktop" (Панель — расширенная версия).
    let layout = "mobile";
    try { layout = (host && host.layout ? host.layout() : parent.document.documentElement.dataset.layout) || "mobile"; } catch (e) {}
    document.documentElement.dataset.layout = layout;
    try {
        const src = parent.document.documentElement.style;
        for (let i = 0; i < src.length; i++) {
            const name = src[i];
            if (name.startsWith("--tg-")) document.documentElement.style.setProperty(name, src.getPropertyValue(name));
        }
    } catch (e) {}
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/style.css";
    document.head.appendChild(link);
    // В style.css у body min-height: 100vh. Внутри окна плагина это высота самого окна: окно подгоняется
    // под страницу, страница — под окно, и оно бесконечно растёт. Здесь высота = только содержимое.
    const fix = document.createElement("style");
    fix.textContent = "html, body { min-height: 0 !important; height: auto !important; }";
    document.head.appendChild(fix);
    document.documentElement.style.background = "transparent";
    document.addEventListener("DOMContentLoaded", () => { document.body.style.background = "transparent"; });

    async function call(name, data = {}) {
        if (!host) throw new Error("Страница плагина должна открываться внутри Cardinal+");
        const r = await host.api(`/api/plugins/${uuid}/call/${name}`, { method: "POST", body: data });
        return r.result;
    }

    window.Plugin = {
        uuid,
        layout,
        call,
        toast: (t) => host && host.toast(t),
        haptic: (t) => host && host.haptic(t),
        confirm: (text) => host && host.confirm ? host.confirm(text) : Promise.resolve(window.confirm(text)),
        openLink: (url) => {
            const tg = parent.Telegram && parent.Telegram.WebApp;
            if (tg) tg.openLink(url); else window.open(url, "_blank");
        },
        // Открывает переписку с покупателем в разделе «Чаты» приложения (id чата FunPay)
        openChat: (chatId, name) => {
            if (host && host.openChat) return host.openChat(chatId, name);
            window.Plugin.openLink(`https://funpay.com/chat/?node=${encodeURIComponent(chatId)}`);
        },
    };
})();
