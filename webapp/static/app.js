(() => {
    "use strict";

    const tg = window.Telegram && window.Telegram.WebApp;
    const inTelegram = !!(tg && tg.initData);
    const root = document.documentElement;

    // ---------- тема ----------
    function applyTheme() {
        const dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
        root.dataset.theme = (inTelegram && tg.colorScheme) || (dark ? "dark" : "light");
        if (inTelegram) {
            const bg = getComputedStyle(root).getPropertyValue("--bg").trim();
            try { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); tg.setBottomBarColor && tg.setBottomBarColor(bg); } catch (e) {}
        }
    }
    if (inTelegram) {
        tg.ready();
        tg.expand();
        try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
        tg.onEvent("themeChanged", applyTheme);
    }
    applyTheme();
    if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);

    // ---------- режим: мобильный / Панель ----------
    const DESKTOP_MIN = 900;
    const getMode = () => { try { return localStorage.getItem("cp_layout") || "auto"; } catch (e) { return "auto"; } };
    const layoutFor = (mode) => mode === "auto" ? (innerWidth >= DESKTOP_MIN ? "desktop" : "mobile") : mode;
    const isDesktop = () => root.dataset.layout === "desktop";
    const desktopPlatform = inTelegram && ["tdesktop", "macos", "weba", "webk", "web", "unigram"].includes(tg.platform);
    const canFullscreen = inTelegram && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") && typeof tg.requestFullscreen === "function";

    function setMode(mode) {
        try { localStorage.setItem("cp_layout", mode); } catch (e) {}
        applyLayout(true);
    }
    function applyLayout(force = false) {
        const next = layoutFor(getMode());
        if (!force && next === root.dataset.layout) return;
        root.dataset.layout = next;
        if (booted) { buildShell(); render(); }
    }
    let resizeTimer;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => { applyLayout(); redrawCharts(); }, 120);
    });

    function initData() {
        if (inTelegram) return tg.initData;
        try { return sessionStorage.getItem("cp_dev_init") || ""; } catch (e) { return ""; }
    }

    // ---------- иконки ----------
    const P = {
        dashboard: '<rect x="3" y="3" width="7.5" height="9" rx="2"/><rect x="13.5" y="3" width="7.5" height="5.5" rx="2"/><rect x="13.5" y="11.5" width="7.5" height="9.5" rx="2"/><rect x="3" y="15" width="7.5" height="6" rx="2"/>',
        home: '<path d="M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1h-5.5v-6.5h-5V21H4a1 1 0 0 1-1-1z"/>',
        wallet: '<rect x="3" y="5.5" width="18" height="14" rx="3"/><path d="M3 10h18M15.5 15h2"/>',
        refresh: '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 3.5V8H16"/>',
        trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
        chart: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
        coins: '<circle cx="9" cy="9" r="6"/><path d="M15.5 9.2A6 6 0 1 1 9.2 15.5"/><path d="M9 6.5v5M7.5 8h2.25a1.25 1.25 0 0 1 0 2.5H7.5"/>',
        clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
        tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.6" cy="7.6" r="1.4"/>',
        up: '<path d="M12 20V5M5.5 11.5 12 5l6.5 6.5"/><path d="M5 20h14"/>',
        send: '<path d="M21 3 10.5 13.5"/><path d="M21 3 14.5 21l-4-7.5L3 9.5z"/>',
        chat: '<path d="M20.5 11.5a8.5 8.5 0 0 1-12.2 7.6L3.5 20.5l1.4-4.6A8.5 8.5 0 1 1 20.5 11.5z"/><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01"/>',
        chevron: '<path d="m9.5 6 6 6-6 6"/>',
        search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
        layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
        restore: '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 3.5V8H8"/><path d="M12 8v4l3 2"/>',
        pause: '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
        smile: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.2a4.2 4.2 0 0 0 7 0"/><path d="M9 9.5h.01M15 9.5h.01"/>',
        sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.3 6.3 2.1 2.1M15.6 15.6l2.1 2.1M6.3 17.7l2.1-2.1M15.6 8.4l2.1-2.1"/>',
        check: '<circle cx="12" cy="12" r="9"/><path d="m8 12.2 2.8 2.8L16 9.5"/>',
        shield: '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6z"/><path d="m8.8 12 2.2 2.2 4.2-4.4"/>',
        eyeoff: '<path d="M3 3l18 18"/><path d="M10.6 5.1A9.7 9.7 0 0 1 12 5c5 0 8.8 4.4 9.8 7a12 12 0 0 1-2.9 4.1M6.5 6.6A12.6 12.6 0 0 0 2.2 12c1 2.6 4.8 7 9.8 7a9.5 9.5 0 0 0 4.3-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
        history: '<path d="M12 7v5l3 2"/><path d="M3.5 12a8.5 8.5 0 1 0 2.4-5.9L3.5 8.5"/><path d="M3.5 4v4.5H8"/>',
        trash: '<path d="M4 7h16M9.5 7V4.5h5V7"/><path d="M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/>',
        ban: '<circle cx="12" cy="12" r="9"/><path d="m5.7 5.7 12.6 12.6"/>',
        belloff: '<path d="M3 3l18 18"/><path d="M8.6 3.9A6 6 0 0 1 18 8.5c0 3 .5 5 1.2 6.4M17 17H3.5S6 15 6 8.5c0-.7.1-1.3.3-1.9"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
        external: '<path d="M14 4h6v6"/><path d="M20 4 10.5 13.5"/><path d="M18.5 14v4.5A1.5 1.5 0 0 1 17 20H5.5A1.5 1.5 0 0 1 4 18.5V7a1.5 1.5 0 0 1 1.5-1.5H10"/>',
        box: '<path d="M21 7.5 12 3 3 7.5v9L12 21l9-4.5z"/><path d="m3 7.5 9 4.5 9-4.5M12 12v9"/>',
        puzzle: '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><path d="M17.25 13.5v7.5M13.5 17.25H21"/>',
        sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
        terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7.5 9.5 3 2.5-3 2.5M13 14.5h4"/>',
        lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
        upload: '<path d="M12 15.5V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v3.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V15"/>',
        alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5h.01"/>',
        plus: '<path d="M12 5v14M5 12h14"/>',
        image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
        inbox: '<path d="M3 13.5 5.5 5h13l2.5 8.5V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M3 13.5h5l1.5 2.5h5l1.5-2.5h5"/>',
        tg: '<path d="m21 4-3 16-6.5-5L9 18.5V14l9-8.5-11.5 7L3 11z"/>',
        monitor: '<rect x="2.5" y="4" width="19" height="12.5" rx="2.5"/><path d="M8 20.5h8M12 16.5v4"/>',
        phone: '<rect x="6.5" y="2.5" width="11" height="19" rx="3"/><path d="M11 18.5h2"/>',
        auto: '<rect x="2.5" y="5" width="13" height="9.5" rx="2"/><path d="M6 18.5h6"/><rect x="15.5" y="9" width="6" height="11" rx="1.6"/>',
        logout: '<path d="M14 4h4.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H14"/><path d="M10 16.5 5.5 12 10 7.5M5.5 12H15"/>',
        maximize: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
        star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
        pencil: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
        users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14a6.5 6.5 0 0 1 3.5 6"/>',
        userx: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="m17 8 4 4M21 8l-4 4"/>',
        pulse: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
        cardinal: '<path d="M4 20c5-1 9-4.5 10.5-10"/><path d="M14.5 10c1.5-.5 3-1.6 3.5-3.5L21 5l-3-.5C17 3 15.5 2.5 14 3c-2 .8-3 3-2.5 5"/><path d="M11.5 8 6 6.5l2.5 4.5"/><circle cx="16" cy="5.5" r=".6"/>',
    };
    // Логотип Cardinal+: птица-кардинал, вместо глаза плюс.
    const LOGO = `<svg class="logo-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M12.5 7.2C15.3 7.6 17.2 9.4 17.6 11.4L22.6 13.7 17.3 16.3C16.2 19.4 13.5 21.4 10.4 21.4 6.6 21.4 4 18.4 4 14.6 4 12.4 4.8 10.6 6.2 9.4 6 7.6 5 5 4.4 2.6 7.6 3.8 10.6 5.4 12.5 7.2Z M12 9.1h1.5v1.45h1.45v1.5h-1.45v1.45h-1.5v-1.45h-1.45v-1.5h1.45Z"/></svg>`;
    const icon = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24">${P[name] || P.sparkle}</svg>`;

    // ---------- утилиты ----------
    const $ = (id) => document.getElementById(id);
    const $view = $("view");
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const haptic = (type = "light") => { try { inTelegram && tg.HapticFeedback.impactOccurred(type); } catch (e) {} };
    const notify = (type) => { try { inTelegram && tg.HapticFeedback.notificationOccurred(type); } catch (e) {} };
    const num = (v, d = 2) => Number(v || 0).toLocaleString("ru-RU", { maximumFractionDigits: d });
    const money = (v, cur = "₽") => `${num(v)} ${cur}`;
    const shortMoney = (v) => v >= 1000 ? `${num(v / 1000, 1)} тыс.` : num(v, 0);
    const plural = (n, a, b, c) => { const m10 = n % 10, m100 = n % 100; return m10 === 1 && m100 !== 11 ? a : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? b : c; };
    const rub = (sum) => (sum && sum["₽"]) || 0;

    let toastTimer;
    function toast(text, kind = "ok") {
        const el = $("toast");
        el.innerHTML = icon(kind === "ok" ? "check" : "alert") + `<span>${esc(text)}</span>`;
        el.classList.add("show");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove("show"), 2300);
    }

    function uptime(sec) {
        const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
        if (d) return `${d} д ${h} ч`;
        if (h) return `${h} ч ${m} мин`;
        return `${Math.max(m, 1)} мин`;
    }
    const sameDay = (a, b) => a.toDateString() === b.toDateString();
    const yesterday = () => { const y = new Date(); y.setDate(y.getDate() - 1); return y; };
    function dayLabel(d) {
        if (sameDay(d, new Date())) return "Сегодня";
        if (sameDay(d, yesterday())) return "Вчера";
        return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" });
    }
    const hm = (d) => d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    function shortTime(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        if (sameDay(d, new Date())) return hm(d);
        if (sameDay(d, yesterday())) return `вчера, ${hm(d)}`;
        return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
    }
    const fullDate = (iso) => iso ? new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) : "—";
    const dayDate = (isoDay) => new Date(isoDay + "T12:00:00");
    function greeting() {
        const h = new Date().getHours();
        return h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
    }
    function deltaBadge(cur, prev, suffix = "") {
        if (!prev) return cur ? `<span class="delta up">+${money(cur)}${suffix}</span>` : `<span class="delta flat">без изменений</span>`;
        const pct = Math.round((cur - prev) / prev * 1000) / 10;
        if (pct === 0) return `<span class="delta flat">0%${suffix}</span>`;
        return `<span class="delta ${pct > 0 ? "up" : "down"}">${pct > 0 ? "+" : ""}${num(pct, 1)}%${suffix}</span>`;
    }

    const PALETTE = [["#f0354b", "#ff7a45"], ["#7b5cf0", "#b25cf0"], ["#2f7cf6", "#21b5e8"], ["#16a36a", "#4cc38a"],
        ["#e07a0b", "#f4b13e"], ["#0ea5a5", "#36c6b4"], ["#d6336c", "#f06595"], ["#5c6ac4", "#8c7ae6"]];
    /** Аватарка аккаунта с FunPay; пока грузится или если её нет — буквы ника. */
    function avatarInner(acc, letters = 1) {
        const txt = esc((acc && acc.username ? acc.username : "C").slice(0, letters).toUpperCase());
        const img = acc && acc.avatar ? `<img src="${esc(acc.avatar)}" alt="" referrerpolicy="no-referrer" decoding="async" onerror="this.remove()">` : "";
        return `<span>${txt}</span>${img}`;
    }
    document.addEventListener("click", (e) => {
        if (!e.target.closest("#my-avatar, #top-me")) return;
        const link = state.account && state.account.profile_link;
        if (link) { haptic(); openLink(link); }
    });

    function gameGradient(name) {
        let h = 7;
        for (const ch of String(name || "?")) h = (h * 33 + ch.charCodeAt(0)) >>> 0;
        const [a, b] = PALETTE[h % PALETTE.length];
        return `linear-gradient(135deg,${a},${b})`;
    }
    function buyerAvatar(name) {
        let h = 0;
        for (const ch of String(name || "?")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
        const [a, b] = PALETTE[h % PALETTE.length];
        return `<div class="buyer" style="background:linear-gradient(135deg,${a},${b})">${esc((name || "?")[0].toUpperCase())}</div>`;
    }

    async function api(path, opts = {}) {
        const headers = { "Content-Type": "application/json", "X-CP": "1" };
        const init = initData();
        if (init) headers["X-Init-Data"] = init;
        const res = await fetch(path, { method: opts.method || "GET", headers, body: opts.body ? JSON.stringify(opts.body) : undefined, credentials: "same-origin" });
        let data = {};
        try { data = await res.json(); } catch (e) {}
        if (!res.ok) {
            // без текста ошибки ответ пришёл не от Cardinal, а от туннеля Cloudflare: значит, Cardinal на компьютере не отвечает
            const err = new Error(data.error || ([502, 504, 530].includes(res.status) ? "Cardinal не отвечает — проверьте, что он запущен на компьютере, и обновите страницу" : `Ошибка ${res.status}`));
            err.status = res.status;
            if (res.status === 401 && !init && booted) showLogin();
            throw err;
        }
        return data;
    }
    // Доступно страницам плагинов (iframe) через plugin-sdk.js
    window.CardinalPlus = {
        api, initData, toast, haptic, confirm: (text) => confirmDialog(text),
        layout: () => root.dataset.layout || "mobile",
        openChat: (id, name) => openChatFromPlugin(id, name),
    };

    const sk = (h, mb = 10, r) => `<div class="skeleton" style="height:${h}px;margin-bottom:${mb}px${r ? `;border-radius:${r}px` : ""}"></div>`;
    const errorBox = (e) => (e.status === 401 || e.status === 403)
        ? `<div class="empty"><div class="e">${icon("lock")}</div><div class="h">Нет доступа</div>${esc(e.message)}</div>`
        : `<div class="error-box">${icon("alert")}<div>${esc(e.message)}</div></div>`;
    const emptyBox = (ic, title, text) => `<div class="empty"><div class="e">${icon(ic)}</div><div class="h">${esc(title)}</div>${text}</div>`;
    // Заголовок страницы: [заголовок ... кнопки] в первой строке, подпись — на всю ширину под ними
    // Замечания по плагину (одинаковые команды с другим плагином, ошибки в боте)
    const warnBadge = (p) => p.warnings && p.warnings.length ? `<span class="badge warn plain" title="${esc(p.warnings.join(" "))}">${icon("alert")}Внимание</span>` : "";
    // Автор вида @ник — ссылка на его Telegram (например, магазин @sqeyeshopbot)
    const credLink = (c) => /^@[A-Za-z0-9_]{4,32}$/.test(String(c || "").trim())
        ? `<a class="cred" data-stop data-tg="https://t.me/${esc(String(c).trim().slice(1))}">${esc(String(c).trim())}</a>` : esc(c);
    // Плагин из магазина без подходящей лицензии
    const licBadge = (p) => p.license && !p.license.ok ? `<span class="badge refunded plain" title="${esc(p.license.text)}">${icon("lock")}нет лицензии</span>` : "";
    const bindTgLinks = (root) => root.querySelectorAll("[data-tg]").forEach((el) => el.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation(); haptic(); openTgLink(el.dataset.tg);
    }));
    // Новая версия плагина записана, но заработает после перезапуска Cardinal
    const pendBadge = (p) => p.pending_update ? `<span class="badge warn plain" title="Новая версия заработает после перезапуска Cardinal">${icon("refresh")}v${esc(p.pending_update.version)}</span>` : "";
    const warnBox = (p) => p.warnings && p.warnings.length ? `<div class="warn-box">${icon("alert")}<div>${p.warnings.map((w) => `<p>${esc(w)}</p>`).join("")}</div></div>` : "";
    const pageHead = (title, sub = "", right = "") => `<div class="page-head"><h1>${esc(title)}</h1>${right ? `<div class="ph-right">${right}</div>` : ""}${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    const sectionHead = (title, link = "") => `<div class="section-head"><h3>${esc(title)}</h3>${link}</div>`;
    const sw = (attrs, checked) => `<label class="switch"><input type="checkbox" ${attrs} ${checked ? "checked" : ""}><span class="slider"></span></label>`;
    const openLink = (url) => { if (inTelegram) tg.openLink(url); else window.open(url, "_blank", "noopener"); };

    // ---------- состояние ----------
    const state = { account: null, uptime: 0, paid: 0, version: "", lastDash: null };
    let booted = false;
    let currentTab = "home";
    let stack = [];
    let renderId = 0;

    // ---------- каркас ----------
    const TABS = [["home", "Главная", "Дашборд", "home", "dashboard"], ["orders", "Заказы", "Заказы", "box", "box"],
        ["chats", "Чаты", "Чаты", "chat", "chat"], ["reviews", "Отзывы", "Отзывы", "star", "star"], ["lots", "Лоты", "Лоты", "tag", "tag"], ["stock", "Склад", "Склад", "inbox", "inbox"],
        ["stats", "Статистика", "Статистика", "chart", "chart"], ["buyers", "Покупатели", "Покупатели", "users", "users"],
        ["plugins", "Плагины", "Плагины", "puzzle", "puzzle"], ["settings", "Настройки", "Настройки", "sliders", "sliders"]];
    const PANEL_ONLY_TABS = ["stock", "stats", "reviews", "buyers"];  // на телефоне их нет в нижнем меню

    function buildShell() {
        $("tabbar").innerHTML = TABS.filter(([id]) => !PANEL_ONLY_TABS.includes(id)).map(([id, label, , ic]) =>
            `<button data-tab="${id}" class="${id === currentTab ? "active" : ""}">${icon(ic)}<span>${label}</span>${id === "chats" ? `<span class="tb-cnt${chatState.unread ? " show" : ""}" id="tb-chats">${chatState.unread || ""}</span>` : ""}</button>`).join("");

        if (!isDesktop()) { $("sidebar").innerHTML = ""; $("topbar").innerHTML = ""; return; }

        const acc = state.account || {};
        $("sidebar").innerHTML = `
            <div class="brand"><div class="mark">${LOGO}</div><span class="txt">Cardinal<span class="plus">+</span></span></div>
            ${TABS.map(([id, , label, , ic]) => `<button class="nav-btn ${id === currentTab ? "active" : ""}" data-tab="${id}">${icon(ic)}<span class="lbl">${label}</span>${id === "orders" ? `<span class="cnt" id="nav-paid">${state.paid || ""}</span>` : ""}${id === "chats" ? `<span class="cnt brand" id="nav-chats">${chatState.unread || ""}</span>` : ""}${id === "stock" ? `<span class="cnt" id="nav-stock"></span>` : ""}</button>`).join("")}
            <div class="spacer"></div>
            <div class="side-card"><div class="t"><span class="pulse"></span>Cardinal работает</div><span id="side-up">${state.uptime ? `${uptime(state.uptime)} · v${esc(state.version)}` : "Загрузка…"}</span></div>
            ${inTelegram ? `<button class="nav-btn" id="nav-browser">${icon("monitor")}<span class="lbl">Открыть в браузере</span></button>` : ""}
            <button class="nav-btn" id="nav-mobile">${icon("phone")}<span class="lbl">Мобильный вид</span></button>
            ${!inTelegram ? `<button class="nav-btn" id="nav-logout">${icon("logout")}<span class="lbl">Выйти</span></button>` : ""}`;

        $("topbar").innerHTML = `
            <label class="search">${icon("search")}<input id="top-q" type="search" placeholder="Поиск заказов по товару, нику, номеру…" autocomplete="off" value="${esc(ordersQuery)}"></label>
            <div class="grow"></div>
            <span class="online"><span class="pulse"></span>Онлайн</span>
            <button class="icon-btn" id="top-refresh" title="Обновить">${icon("refresh")}</button>
            <button class="me" id="top-me" title="${esc(acc.username || "")} — профиль на FunPay">${avatarInner(acc, 2)}</button>`;

        $("top-q").addEventListener("keydown", (e) => {
            if (e.key !== "Enter") return;
            ordersQuery = e.target.value;
            if (currentTab === "orders" && !stack.length) render(); else setTab("orders");
        });
        $("top-refresh").addEventListener("click", () => render(true));
        updateStockBadge();
        $("nav-mobile").addEventListener("click", () => setMode("mobile"));
        const nb = $("nav-browser");
        if (nb) nb.addEventListener("click", openInBrowser);
        const nl = $("nav-logout");
        if (nl) nl.addEventListener("click", logout);
    }

    function updateChrome() {
        const paid = $("nav-paid");
        if (paid) paid.textContent = state.paid || "";
        const up = $("side-up");
        if (up && state.uptime) up.textContent = `${uptime(state.uptime)} · v${state.version}`;
        const me = document.querySelector(".topbar .me");
        if (me && state.account) me.innerHTML = avatarInner(state.account, 2);
    }

    document.addEventListener("click", (e) => {
        const b = e.target.closest("[data-tab]");
        if (!b || !b.closest("#tabbar, #sidebar")) return;
        haptic("light");
        if (b.dataset.tab === currentTab && !stack.length) return;
        setTab(b.dataset.tab);
    });

    function setTab(tab) {
        currentTab = tab;
        stack = [];
        document.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
        updateBackButton();
        render();
    }
    function push(screen) { stack.push(screen); updateBackButton(); render(); }
    function back() {
        if (closeSheet()) return;
        stack.pop(); updateBackButton(); render();
    }
    function updateBackButton() {
        if (!inTelegram) return;
        if (stack.length || sheetOpen) tg.BackButton.show(); else tg.BackButton.hide();
    }
    if (inTelegram) tg.BackButton.onClick(back);

    function paint(html) {
        $view.innerHTML = html;
        $view.classList.remove("screen-in");
        void $view.offsetWidth;
        $view.classList.add("screen-in");
    }

    function render(refresh = false) {
        const id = ++renderId;
        stopChatTimers();
        document.body.classList.remove("chat-open");
        charts.length = 0;
        removeAzIndex();
        if (!refresh) window.scrollTo(0, 0);
        const screen = stack.length ? stack[stack.length - 1] : { type: currentTab };
        const renderers = { home: renderHome, orders: renderOrders, chats: renderChats, chat: renderChat, lots: renderLots, plugins: renderPlugins, settings: renderSettings, plugin: renderPlugin, blacklist: renderBlacklist, stock: renderStock, stockfile: renderStockFile, stats: renderStats, reviews: renderReviews, buyers: renderBuyers, schedule: renderSchedule, audit: renderAudit };
        renderers[screen.type](screen, () => id === renderId, refresh);
    }

    async function openInBrowser() {
        haptic();
        try {
            const r = await api("/api/login-link", { method: "POST" });
            openLink(r.url);
            toast("Ссылка для входа открыта в браузере");
        } catch (e) { toast(e.message, "err"); }
    }
    async function logout() {
        try { await api("/api/logout", { method: "POST" }); } catch (e) {}
        showLogin();
    }
    function goFullscreen() {
        haptic();
        try { localStorage.setItem("cp_layout", "auto"); } catch (e) {}
        try { tg.requestFullscreen(); } catch (e) { toast("Обновите Telegram, чтобы развернуть приложение", "err"); }
    }

    // ---------- bottom sheet (телефон) ----------
    let sheetOpen = false;
    function openSheet(html) {
        closeSheet(true);
        const bd = document.createElement("div");
        bd.className = "sheet-backdrop";
        const sh = document.createElement("div");
        sh.className = "sheet";
        sh.innerHTML = `<div class="grab"></div>${html}`;
        document.body.append(bd, sh);
        requestAnimationFrame(() => { bd.classList.add("show"); sh.classList.add("show"); });
        bd.addEventListener("click", () => closeSheet());
        sheetOpen = true;
        updateBackButton();
        return sh;
    }
    function closeSheet(instant = false) {
        const sh = document.querySelector(".sheet"), bd = document.querySelector(".sheet-backdrop");
        if (!sh) return false;
        sheetOpen = false;
        if (instant) { sh.remove(); bd && bd.remove(); }
        else {
            sh.classList.remove("show"); bd && bd.classList.remove("show");
            setTimeout(() => { sh.remove(); bd && bd.remove(); }, 300);
        }
        updateBackButton();
        return true;
    }

    // ---------- график ----------
    const charts = [];
    function redrawCharts() { charts.forEach((c) => c.draw()); }

    function niceMax(v) {
        if (v <= 0) return 1000;
        const p = Math.pow(10, Math.floor(Math.log10(v)));
        for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
        return 10 * p;
    }

    /** Плавный график выручки за 7 дней. opts: {height, compact, selected, onSelect} */
    function createChart(el, week, opts) {
        const chart = {
            selected: opts.selected ?? week.length - 1,
            draw() {
                const W = Math.max(260, el.clientWidth || 600), H = opts.height;
                const compact = !!opts.compact;
                const padL = compact ? 14 : 52, padR = compact ? 14 : 18, padT = 30, padB = 28;
                const vals = week.map((d) => rub(d.sum));
                const max = niceMax(Math.max(...vals) * 1.12);
                const iw = W - padL - padR, ih = H - padT - padB;
                const n = vals.length;
                const xs = vals.map((_, i) => padL + (n === 1 ? iw / 2 : i * iw / (n - 1)));
                const ys = vals.map((v) => padT + (1 - v / max) * ih);
                const bottom = padT + ih;
                const clampY = (y) => Math.min(bottom, Math.max(padT - 6, y));
                let d = `M${xs[0]},${ys[0]}`;
                for (let i = 0; i < n - 1; i++) {
                    const x0 = xs[i - 1] ?? xs[i], y0 = ys[i - 1] ?? ys[i], x3 = xs[i + 2] ?? xs[i + 1], y3 = ys[i + 2] ?? ys[i + 1];
                    const c1x = xs[i] + (xs[i + 1] - x0) / 6, c1y = clampY(ys[i] + (ys[i + 1] - y0) / 6);
                    const c2x = xs[i + 1] - (x3 - xs[i]) / 6, c2y = clampY(ys[i + 1] - (y3 - ys[i]) / 6);
                    d += ` C${c1x},${c1y} ${c2x},${c2y} ${xs[i + 1]},${ys[i + 1]}`;
                }
                const area = `${d} L${xs[n - 1]},${bottom} L${xs[0]},${bottom} Z`;
                const step = n > 1 ? iw / (n - 1) : iw;
                const colW = Math.min(64, Math.max(30, step * 0.62));
                const sel = this.selected;
                const avg = vals.reduce((a, b) => a + b, 0) / (n || 1);
                const gid = `g${Math.random().toString(36).slice(2, 8)}`;
                const todayIso = new Date().toISOString().slice(0, 10);

                let grid = "";
                if (!compact) {
                    for (let k = 0; k <= 4; k++) {
                        const y = padT + ih * (1 - k / 4);
                        grid += `<line class="grid-l" x1="${padL}" x2="${W - padR}" y1="${y}" y2="${y}"/>`;
                        grid += `<text class="axis-t" x="${padL - 10}" y="${y + 4}" text-anchor="end">${k ? shortMoney(max * k / 4) : "0"}</text>`;
                    }
                    if (avg > 0) {
                        const ay = padT + (1 - avg / max) * ih;
                        grid += `<line class="avg-l" x1="${padL}" x2="${W - padR}" y1="${ay}" y2="${ay}"/>`;
                        grid += `<text class="axis-t" x="${W - padR}" y="${ay - 6}" text-anchor="end">Среднее ${money(Math.round(avg))}</text>`;
                    }
                } else {
                    grid += `<line class="grid-l" x1="${padL}" x2="${W - padR}" y1="${bottom}" y2="${bottom}"/>`;
                }

                const xLabels = week.map((w, i) => {
                    const dt = dayDate(w.date);
                    const isToday = w.date === todayIso;
                    const txt = compact ? (isToday ? "Сег" : dt.toLocaleDateString("ru-RU", { weekday: "short" }).replace(".", ""))
                        : dt.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", "");
                    return `<text class="axis-t" x="${xs[i]}" y="${H - 6}" text-anchor="middle" style="${i === sel ? "fill:var(--text);font-weight:700" : ""}">${txt}</text>`;
                }).join("");

                const labels = vals.map((v, i) => (!compact || i === sel)
                    ? `<text class="val-t ${i === sel ? "sel" : ""}" x="${xs[i]}" y="${ys[i] - 12}" text-anchor="middle">${num(v, 0)}</text>` : "").join("");
                const dots = vals.map((v, i) => `<circle class="dot ${i === sel ? "sel" : ""}" cx="${xs[i]}" cy="${ys[i]}" r="${i === sel ? 6 : 4}"/>`).join("");
                const hits = vals.map((_, i) => `<rect class="hit" data-i="${i}" x="${xs[i] - step / 2}" y="0" width="${step}" height="${H}"/>`).join("");

                el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}">
                    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" style="stop-color:var(--brand);stop-opacity:.28"/>
                        <stop offset="100%" style="stop-color:var(--brand);stop-opacity:0"/></linearGradient></defs>
                    <rect class="col-hl" x="${xs[sel] - colW / 2}" y="${padT - 26}" width="${colW}" height="${bottom - padT + 26}" rx="12"/>
                    ${grid}
                    <path d="${area}" fill="url(#${gid})"/>
                    <path class="line" d="${d}"/>
                    ${dots}${labels}${xLabels}${hits}
                </svg>`;
                el.querySelectorAll(".hit").forEach((r) => r.addEventListener("click", () => {
                    const i = +r.dataset.i;
                    if (i === this.selected) return;
                    haptic("light");
                    this.selected = i;
                    this.draw();
                    opts.onSelect && opts.onSelect(i);
                }));
            },
        };
        charts.push(chart);
        chart.draw();
        return chart;
    }

    function weekStats(week) {
        const sums = week.map((d) => rub(d.sum));
        const total = sums.reduce((a, b) => a + b, 0);
        const count = week.reduce((a, d) => a + d.count, 0);
        let best = 0;
        sums.forEach((v, i) => { if (v > sums[best]) best = i; });
        return { sums, total, count, avg: total / (week.length || 1), best };
    }

    // ---------- заказы: общие ----------
    const STATUS = { paid: "Оплачен", closed: "Закрыт", refunded: "Возврат", partially_refunded: "Частичный возврат", unpaid: "Не оплачен" };
    const statusBadge = (s) => `<span class="badge ${esc(s)}">${STATUS[s] || esc(s)}</span>`;
    const orderRow = (o) => `
        <button class="item clickable" data-order="${esc(o.id)}">
            ${buyerAvatar(o.buyer)}
            <div class="body">
                <div class="t"><span class="txt">${esc(o.description || o.subcategory || "Заказ")}</span></div>
                <div class="s">${esc(o.buyer)}${o.blacklisted ? ` · <span style="color:var(--red);font-weight:600">в ЧС</span>` : ""} · ${esc(shortTime(o.date))}</div>
            </div>
            <div class="right"><div class="price tnum">${money(o.price, o.currency)}</div>${statusBadge(o.status)}</div>
        </button>`;
    const orderTable = (items, selId) => `
        <div class="table-wrap"><table class="table">
            <thead><tr><th>Заказ</th><th>Покупатель</th><th>Дата</th><th>Статус</th><th class="num">Сумма</th></tr></thead>
            <tbody>${items.map((o) => `
                <tr data-order="${esc(o.id)}" class="${o.id === selId ? "sel" : ""}">
                    <td><div class="desc">${esc(o.description || o.subcategory || "Заказ")}</div><div class="id">#${esc(o.id)}</div></td>
                    <td><div class="who">${buyerAvatar(o.buyer)}<span>${esc(o.buyer)}</span>${o.blacklisted ? `<span class="badge refunded plain" title="В чёрном списке">ЧС</span>` : ""}</div></td>
                    <td class="muted">${esc(shortTime(o.date))}</td>
                    <td>${statusBadge(o.status)}</td>
                    <td class="num price tnum">${money(o.price, o.currency)}</td>
                </tr>`).join("")}</tbody>
        </table></div>`;
    const banLabel = (o) => o.blacklisted ? `${icon("check")}Убрать из чёрного списка` : `${icon("userx")}В чёрный список`;
    const orderActions = (o) => `
        <button class="btn" data-act="order">${icon("external")}Открыть заказ на FunPay</button>
        <button class="btn secondary" data-act="chat">${icon("chat")}Чат с покупателем</button>
        <button class="btn secondary" data-act="ban" style="color:${o.blacklisted ? "var(--text)" : "var(--red)"}">${banLabel(o)}</button>`;
    function bindOrderActions(scope, o, onBanChange) {
        scope.querySelector('[data-act="order"]').onclick = () => openLink(`https://funpay.com/orders/${o.id}/`);
        scope.querySelector('[data-act="chat"]').onclick = () => openLink(`https://funpay.com/chat/?node=${encodeURIComponent(o.chat_id)}`);
        const ban = scope.querySelector('[data-act="ban"]');
        ban.onclick = async () => {
            const adding = !o.blacklisted;
            const ok = await confirmDialog(adding
                ? `Добавить ${o.buyer} в чёрный список? К нему применятся ограничения из Настроек → Чёрный список.`
                : `Убрать ${o.buyer} из чёрного списка?`);
            if (!ok) return;
            ban.disabled = true;
            try {
                await blacklistChange(adding ? "add" : "remove", o.buyer);
                o.blacklisted = adding;
                ban.innerHTML = banLabel(o);
                ban.style.color = adding ? "var(--text)" : "var(--red)";
                onBanChange && onBanChange(o.buyer, adding);
            } catch (e) { toast(e.message, "err"); notify("error"); }
            finally { ban.disabled = false; }
        };
    }
    function orderDetailHtml(o) {
        return `
            <div class="head">
                ${buyerAvatar(o.buyer)}
                <div style="flex:1;min-width:0"><div class="title tnum">${money(o.price, o.currency)}</div><div class="sub">Заказ #${esc(o.id)}</div></div>
                ${statusBadge(o.status)}
            </div>
            <div class="descr">${esc(o.description || "Без описания")}</div>
            <div class="kv-row"><span class="k">Покупатель</span><span class="v">${esc(o.buyer)}</span></div>
            <div class="kv-row"><span class="k">Категория</span><span class="v">${esc(o.subcategory || "—")}</span></div>
            <div class="kv-row"><span class="k">Количество</span><span class="v">${esc(o.amount ?? "—")}</span></div>
            <div class="kv-row"><span class="k">Дата</span><span class="v">${esc(fullDate(o.date))}</span></div>
            <div style="margin-top:14px">${orderActions(o)}</div>`;
    }
    function showOrderSheet(o, onBanChange) {
        haptic();
        const sh = openSheet(`<div class="detail">${orderDetailHtml(o)}</div>`);
        bindOrderActions(sh, o, onBanChange);
    }

    async function toggleModule(t, key) {
        const next = !t.classList.contains("on");
        haptic("medium");
        t.disabled = true;
        const set = (v) => { t.classList.toggle("on", v); const s = t.querySelector(".s"); if (s) s.textContent = v ? "Включено" : "Выключено"; const i = t.querySelector("input"); if (i) i.checked = v; };
        set(next);
        try {
            const r = await api("/api/settings", { method: "POST", body: { section: "FunPay", option: key, value: next } });
            set(r.value);
        } catch (e) { set(!next); toast(e.message, "err"); notify("error"); }
        finally { t.disabled = false; }
    }

    // ---------- Главная ----------
    async function loadDashboard(alive) {
        const d = await api("/api/dashboard");
        if (!alive()) return null;
        state.account = d.account;
        state.uptime = d.uptime;
        state.paid = d.orders.paid;
        if (d.stock) { state.stock = d.stock; updateStockBadge(); }
        state.lastDash = new Date();
        try { const me = await api("/api/me"); state.version = me.version; } catch (e) {}
        updateChrome();
        return d;
    }

    function renderHome(screen, alive, refresh) {
        return isDesktop() ? homeDesktop(alive, refresh) : homeMobile(alive);
    }

    async function homeMobile(alive) {
        paint(sk(48, 18, 15) + sk(178, 10, 22) + `<div class="grid">${sk(104, 0)}${sk(104, 0)}${sk(104, 0)}${sk(104, 0)}</div>` + "<br>" + sk(190));
        let d;
        try { d = await loadDashboard(alive); } catch (e) { if (alive()) paint(errorBox(e)); return; }
        if (!d) return;

        const acc = d.account || {};
        const b = d.balance;
        const week = d.orders.week || [];
        const ws = weekStats(week);
        const [intPart, fracPart] = b ? num(b.rub).split(",") : ["0"];
        const extra = b ? [b.usd ? `$${num(b.usd)}` : "", b.eur ? `€${num(b.eur)}` : ""].filter(Boolean) : [];
        const todayRub = rub(d.orders.today.sum);
        const recent = d.orders.recent || [];

        const tile = (key, label, ic) => `
            <button class="tile ${d.modules[key] ? "on" : ""}" data-mod="${key}">
                <div class="ic">${icon(ic)}</div>
                <div><div class="t">${label}</div><div class="s">${d.modules[key] ? "Включено" : "Выключено"}</div></div>
            </button>`;
        const chartCap = (i) => {
            const day = week[i];
            if (!day) return "";
            const lbl = i === week.length - 1 ? "Сегодня" : dayDate(day.date).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "short" });
            return `<div class="big tnum">${money(rub(day.sum))}</div><div class="cap">${esc(lbl)}<br>${day.count} ${plural(day.count, "заказ", "заказа", "заказов")}</div>`;
        };

        paint(`
            <div class="profile">
                <button class="avatar" id="my-avatar" aria-label="Профиль на FunPay">${avatarInner(acc, 1)}</button>
                <div class="who">
                    <div class="name">${esc(acc.username || "Аккаунт")}</div>
                    <div class="pill-status"><span class="pulse"></span>Работает ${uptime(d.uptime)}</div>
                </div>
                ${desktopPlatform && canFullscreen ? `<button class="icon-btn" id="fullscreen" aria-label="Развернуть">${icon("maximize")}</button>` : ""}
                <button class="icon-btn" id="reload-home" aria-label="Обновить">${icon("refresh")}</button>
            </div>

            ${guardBanner(d.guard)}${updBanner(d.plus_update)}
            <div class="hero">
                <div class="top">
                    <div class="label">${icon("wallet")}Баланс</div>
                    ${b ? `<button class="glass refresh" id="refresh-balance" aria-label="Обновить баланс">${icon("refresh")}</button>` : ""}
                </div>
                <div class="amount tnum">${b ? `${intPart}${fracPart ? `<span style="opacity:.7">,${fracPart}</span>` : ""}<span class="cur">₽</span>` : "—"}</div>
                <div class="foot">
                    ${b ? `<span class="glass"><span class="k">К выводу</span>${money(b.rub_available)}</span>` : `<span class="glass">Баланс ещё загружается</span>`}
                    ${extra.map((x) => `<span class="glass">${x}</span>`).join("")}
                </div>
            </div>

            <div class="grid">
                <div class="stat"><div class="ic tint-brand">${icon("trend")}</div><div><div class="v tnum">${d.orders.today.count}</div><div class="l">${plural(d.orders.today.count, "Продажа", "Продажи", "Продаж")} сегодня</div></div></div>
                <div class="stat"><div class="ic tint-green">${icon("coins")}</div><div><div class="v tnum">${money(todayRub)}</div><div class="l">Выручка сегодня${d.orders.today.profit ? ` · прибыль ${money(d.orders.today.profit.profit)}` : ""}</div></div></div>
                <div class="stat"><div class="ic tint-amber">${icon("clock")}</div><div><div class="v tnum">${d.orders.paid}</div><div class="l">Ждут выполнения</div></div></div>
                <div class="stat"><div class="ic tint-blue">${icon("tag")}</div><div><div class="v tnum">${d.lots.active ?? "—"} <small>/ ${d.lots.total ?? "—"}</small></div><div class="l">Активных лотов</div></div></div>
            </div>
            ${d.orders.error ? `<div class="note">Не удалось загрузить заказы: ${esc(d.orders.error)}</div>` : ""}
            <div style="margin-top:14px">${planBoxHtml(d.plan)}</div>

            ${sectionHead("Продажи за неделю", `<span class="cap" style="color:var(--muted);font-size:13px">${money(ws.total)}</span>`)}
            <div class="chart-card">
                <div class="chart-head" id="m-cap">${chartCap(week.length - 1)}</div>
                <div class="chart" id="m-chart"></div>
            </div>

            ${sectionHead("Автоматизация")}
            <div class="tiles">
                ${tile("autoRaise", "Автоподнятие", "up")}
                ${tile("autoDelivery", "Автовыдача", "send")}
                ${tile("autoResponse", "Автоответ", "chat")}
            </div>

            ${sectionHead("Последние заказы", recent.length ? `<button class="link" data-go="orders">Все${icon("chevron")}</button>` : "")}
            ${recent.length ? `<div class="list">${recent.map(orderRow).join("")}</div>` : emptyBox("inbox", "Заказов пока нет", "Новые продажи появятся здесь")}

            ${sectionHead("Ещё")}
            <div class="list">
                <button class="item clickable" data-push="reviews">
                    <div class="ic tint-amber">${icon("star")}</div>
                    <div class="body"><div class="t">Отзывы</div><div class="s">${d.reviews && d.reviews.total ? `★ ${num(d.reviews.avg, 1)} · ${d.reviews.total} ${plural(d.reviews.total, "отзыв", "отзыва", "отзывов")}${d.reviews.no_reply ? ` · без ответа ${d.reviews.no_reply}` : ""}` : "Ответы на отзывы, плохие оценки"}</div></div>
                    <div class="chev">${icon("chevron")}</div>
                </button>
                <button class="item clickable" data-go="plugins">
                    <div class="ic tint-violet">${icon("puzzle")}</div>
                    <div class="body"><div class="t">Плагины</div><div class="s">Включено ${d.plugins.enabled} из ${d.plugins.total}</div></div>
                    <div class="chev">${icon("chevron")}</div>
                </button>
                <button class="item clickable" id="to-desktop">
                    <div class="ic tint-blue">${icon("monitor")}</div>
                    <div class="body"><div class="t">Панель управления</div><div class="s">${inTelegram ? "Открыть в браузере или переключить вид" : "Переключить вид"}</div></div>
                    <div class="chev">${icon("chevron")}</div>
                </button>
            </div>`);

        if (week.length) createChart($("m-chart"), week, { height: 150, compact: true, onSelect: (i) => { $("m-cap").innerHTML = chartCap(i); } });
        $view.querySelectorAll("[data-mod]").forEach((t) => t.addEventListener("click", () => toggleModule(t, t.dataset.mod)));
        $view.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => { haptic(); setTab(el.dataset.go); }));
        $view.querySelectorAll("[data-order]").forEach((el) => el.addEventListener("click", () => showOrderSheet(recent.find((o) => o.id === el.dataset.order))));
        $("reload-home").addEventListener("click", () => { haptic(); render(); });
        if ($("upd-banner")) $("upd-banner").addEventListener("click", updateSheet);
        $("to-desktop").addEventListener("click", () => { haptic(); setTab("settings"); });
        $view.querySelectorAll("[data-push]").forEach((el) => el.addEventListener("click", () => { haptic(); push({ type: el.dataset.push }); }));
        bindPlan(alive, d.plan);
        const fs = $("fullscreen");
        if (fs) fs.addEventListener("click", goFullscreen);
        bindBalanceRefresh(alive);
    }

    function bindBalanceRefresh(alive) {
        const rb = $("refresh-balance");
        if (!rb) return;
        rb.addEventListener("click", async () => {
            haptic(); rb.classList.add("spin"); rb.disabled = true;
            try { await api("/api/balance/refresh", { method: "POST" }); toast("Баланс обновлён"); notify("success"); if (alive()) render(true); }
            catch (e) { toast(e.message, "err"); rb.classList.remove("spin"); rb.disabled = false; }
        });
    }

    async function homeDesktop(alive) {
        paint(sk(70, 18, 12) + sk(70, 14) + `<div class="kpis">${sk(112, 0)}${sk(112, 0)}${sk(112, 0)}${sk(112, 0)}</div>` +
            `<div class="row2">${sk(400, 0)}${sk(400, 0)}</div>`);
        let d;
        try { d = await loadDashboard(alive); } catch (e) { if (alive()) paint(errorBox(e)); return; }
        if (!d) return;

        const acc = d.account || {};
        const b = d.balance;
        const week = d.orders.week || [];
        const ws = weekStats(week);
        const todayRub = rub(d.orders.today.sum);
        const yRub = week.length > 1 ? rub(week[week.length - 2].sum) : 0;
        const recent = d.orders.recent || [];
        const now = new Date();
        const dateStr = now.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
        const lotsPct = d.lots.total ? Math.round((d.lots.active || 0) / d.lots.total * 100) : 0;

        const automation = [["autoRaise", "Автоподнятие", "up", "brand"], ["autoDelivery", "Автовыдача", "send", "green"], ["autoResponse", "Автоответчик", "chat", "blue"]];
        const allOn = automation.every(([k]) => d.modules[k]);

        const dayPanel = (i) => {
            const day = week[i];
            if (!day) return "";
            const v = rub(day.sum);
            const prev = i > 0 ? rub(week[i - 1].sum) : 0;
            const share = ws.total ? Math.round(v / ws.total * 100) : 0;
            const prevName = i > 0 ? dayDate(week[i - 1].date).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", "") : "";
            return `
                <div class="label-sm">Выбранный день</div>
                <div class="day">${esc(dayDate(day.date).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }))}</div>
                <div class="hero-sm">
                    <div class="k">Выручка за день</div>
                    <div class="v tnum">${money(v)}</div>
                    ${i > 0 ? deltaBadge(v, prev, ` к ${prevName}`) : ""}
                </div>
                <div class="kv-row"><span class="k">Продаж</span><span class="v tnum">${day.count}</span></div>
                <div class="kv-row"><span class="k">Средний чек</span><span class="v tnum">${day.count ? money(Math.round(v / day.count)) : "—"}</span></div>
                <div class="share">
                    <div class="top"><span>Доля выручки недели</span><b>${share}%</b></div>
                    <div class="track"><i style="width:${share}%"></i></div>
                </div>
                <div class="hint">Нажмите на день на графике, чтобы увидеть подробности.</div>`;
        };

        paint(`
            <div class="d-head">
                <div>
                    <div class="date">${esc(dateStr[0].toUpperCase() + dateStr.slice(1))}</div>
                    <h1>${greeting()}, ${esc(acc.username || "продавец")}</h1>
                    <div class="sub">Сегодня ${d.orders.today.count} ${plural(d.orders.today.count, "продажа", "продажи", "продаж")} на ${money(todayRub)}</div>
                </div>
                <div class="upd"><span class="pulse"></span>Обновлено в ${hm(state.lastDash)}<button class="icon-btn" id="reload-home" title="Обновить">${icon("refresh")}</button></div>
            </div>

            ${guardBanner(d.guard)}${updBanner(d.plus_update)}
            <div class="banner">
                <div class="ring">${icon("shield")}</div>
                <div class="grow">
                    <div class="t">${allOn ? "Cardinal работает, автоматизация включена" : "Cardinal работает"}</div>
                    <div class="s">Аптайм ${uptime(d.uptime)} · плагинов включено ${d.plugins.enabled} из ${d.plugins.total}${allOn ? "" : " · часть автоматизации выключена"}${d.waiting ? ` · <a class="link-btn" data-go="chats">ждут ответа: ${d.waiting}</a>` : ""}</div>
                </div>
                <button class="btn-sm" data-go="settings">Настройки${icon("chevron")}</button>
            </div>

            <div class="kpis">
                <div class="kpi">
                    <div class="h"><div class="ic tint-brand">${icon("trend")}</div>Сегодня</div>
                    <div class="v tnum">${money(todayRub)}</div>
                    <div class="f">${d.orders.today.count} ${plural(d.orders.today.count, "продажа", "продажи", "продаж")} ${deltaBadge(todayRub, yRub, " к вчера")}${d.orders.today.profit ? `<span class="muted" title="Чистая прибыль: выручка минус себестоимость">прибыль ${money(d.orders.today.profit.profit)}</span>` : ""}</div>
                </div>
                <div class="kpi">
                    <div class="h"><div class="ic tint-green">${icon("wallet")}</div>Баланс${b ? `<button class="btn-sm" id="refresh-balance" style="margin-left:auto;padding:5px 7px" title="Обновить баланс">${icon("refresh")}</button>` : ""}</div>
                    <div class="v tnum">${b ? money(b.rub) : "—"}</div>
                    <div class="f">${b ? `К выводу ${money(b.rub_available)}${b.usd ? ` · $${num(b.usd)}` : ""}${b.eur ? ` · €${num(b.eur)}` : ""}` : "Ещё загружается"}</div>
                </div>
                <div class="kpi">
                    <div class="h"><div class="ic tint-amber">${icon("clock")}</div>Ждут выполнения</div>
                    <div class="v tnum">${d.orders.paid}</div>
                    <div class="f">${d.orders.paid ? `<button class="btn-sm" data-go="orders" style="padding:4px 9px;font-size:12.5px">Открыть заказы</button>` : "Все заказы выполнены"}</div>
                </div>
                <div class="kpi">
                    <div class="h"><div class="ic tint-blue">${icon("tag")}</div>Активные лоты</div>
                    <div class="v tnum">${d.lots.active ?? "—"} <small>из ${d.lots.total ?? "—"}</small></div>
                    <div class="f"><div class="bar-t"><i style="width:${lotsPct}%"></i></div>${lotsPct}%<button class="btn-sm" data-go="lots" style="padding:4px 9px;font-size:12.5px">Управлять</button></div>
                </div>
            </div>
            ${d.orders.error ? `<div class="error-box" style="margin-bottom:14px">${icon("alert")}<div>Не удалось загрузить заказы: ${esc(d.orders.error)}</div></div>` : ""}
            ${planBoxHtml(d.plan)}

            <div class="row2">
                <div class="panel">
                    <div class="panel-h">
                        <div class="ic tint-brand">${icon("chart")}</div>
                        <div class="grow"><div class="t">Выручка за 7 дней</div><div class="s">${week.length ? `${esc(dayDate(week[0].date).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }))} — ${esc(dayDate(week[week.length - 1].date).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" }))} · без возвратов` : ""}</div></div>
                    </div>
                    <div class="sum-tabs">
                        <div class="sum-tab main"><div class="k">Выручка</div><div class="v tnum">${money(ws.total)}</div></div>
                        <div class="sum-tab"><div class="k">Заказов</div><div class="v tnum">${ws.count}</div></div>
                        <div class="sum-tab"><div class="k">В среднем в день</div><div class="v tnum">${money(Math.round(ws.avg))}</div></div>
                        <div class="sum-tab"><div class="k">Лучший день</div><div class="v tnum">${week.length ? `${esc(dayDate(week[ws.best].date).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", ""))} <small>${money(ws.sums[ws.best])}</small>` : "—"}</div></div>
                    </div>
                    <div class="chart" id="d-chart"></div>
                </div>
                <div class="panel day-panel" id="day-panel">${dayPanel(week.length - 1)}</div>
            </div>

            <div class="row2">
                <div class="panel">
                    <div class="panel-h">
                        <div class="ic tint-amber">${icon("box")}</div>
                        <div class="grow"><div class="t">Последние заказы</div><div class="s">Нажмите на заказ, чтобы открыть подробности</div></div>
                        <button class="btn-sm" data-go="orders">Все заказы${icon("chevron")}</button>
                    </div>
                    ${recent.length ? orderTable(recent) : emptyBox("inbox", "Заказов пока нет", "Новые продажи появятся здесь")}
                </div>
                <div class="panel">
                    <div class="panel-h">
                        <div class="ic tint-violet">${icon("sparkle")}</div>
                        <div class="grow"><div class="t">Автоматизация</div><div class="s">Применяется сразу</div></div>
                    </div>
                    ${automation.map(([k, label, ic, tint]) => `
                        <div class="item tile-row ${d.modules[k] ? "on" : ""}" data-mod="${k}" style="padding:10px 2px;min-height:52px">
                            <div class="ic tint-${tint}">${icon(ic)}</div>
                            <div class="body"><div class="t">${label}</div><div class="s">${d.modules[k] ? "Включено" : "Выключено"}</div></div>
                            ${sw(`data-modsw="${k}"`, d.modules[k])}
                        </div>`).join("")}
                    <button class="item clickable" data-go="plugins" style="padding:10px 2px;min-height:52px">
                        <div class="ic tint-gray">${icon("puzzle")}</div>
                        <div class="body"><div class="t">Плагины</div><div class="s">Включено ${d.plugins.enabled} из ${d.plugins.total}</div></div>
                        <div class="chev">${icon("chevron")}</div>
                    </button>
                </div>
            </div>`);

        if (week.length) createChart($("d-chart"), week, { height: 260, onSelect: (i) => { $("day-panel").innerHTML = dayPanel(i); } });
        $view.querySelectorAll("[data-modsw]").forEach((inp) => inp.addEventListener("change", (e) => {
            e.preventDefault();
            inp.checked = !inp.checked;  // переключит toggleModule
            toggleModule(inp.closest("[data-mod]"), inp.dataset.modsw);
        }));
        $view.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => setTab(el.dataset.go)));
        $view.querySelectorAll("tr[data-order]").forEach((el) => el.addEventListener("click", () => {
            selectedOrderId = el.dataset.order;
            setTab("orders");
        }));
        $("reload-home").addEventListener("click", () => render(true));
        if ($("upd-banner")) $("upd-banner").addEventListener("click", updateSheet);
        bindBalanceRefresh(alive);
        bindPlan(alive, d.plan);
    }

    // ---------- Заказы ----------
    let ordersFilter = "";
    let ordersQuery = "";
    let selectedOrderId = null;

    async function renderOrders(_, alive, refresh = false) {
        const desk = isDesktop();
        paint(pageHead("Заказы") + sk(44, 12, 14) + sk(desk ? 520 : 64 * 6, 10));
        let d;
        try { d = await api(`/api/orders${refresh ? "?refresh=1" : ""}`); }
        catch (e) { if (alive()) paint(pageHead("Заказы") + errorBox(e)); return; }
        if (!alive()) return;

        const all = d.orders;
        const counts = d.counts || {};
        state.paid = counts.paid || 0;
        updateChrome();
        const chips = [["", "Все"], ["paid", "Ждут"], ["closed", "Закрытые"], ["refunded", "Возвраты"]];
        const chipsHtml = `<div class="chips">${chips.map(([v, l]) => `<button class="chip ${v === ordersFilter ? "active" : ""}" data-f="${v}">${l}<span class="n">${counts[v] || 0}</span></button>`).join("")}</div>`;
        const searchHtml = `<label class="search">${icon("search")}<input id="q" type="search" placeholder="Поиск по товару, нику или номеру" value="${esc(ordersQuery)}" autocomplete="off"></label>`;
        const sub = `${all.length} ${plural(all.length, "заказ", "заказа", "заказов")} за последнее время`;
        const reloadBtn = `<button class="icon-btn" id="reload" aria-label="Обновить">${icon("refresh")}</button>`;

        if (desk) {
            paint(`${pageHead("Заказы", sub, reloadBtn)}
                <div class="toolbar">${searchHtml}${chipsHtml}</div>
                <div class="orders-layout">
                    <div class="panel" id="orders-list" style="padding:12px 8px 6px"></div>
                    <div class="panel detail sticky" id="order-detail"></div>
                </div>`);
        } else {
            paint(`${pageHead("Заказы", sub, reloadBtn)}${searchHtml}${chipsHtml}<div id="orders-list"></div>`);
        }

        const listEl = $("orders-list");
        const filtered = () => {
            const q = ordersQuery.trim().toLowerCase();
            return all.filter((o) => (!ordersFilter || o.status === ordersFilter) &&
                (!q || [o.description, o.buyer, o.id, o.subcategory].some((x) => String(x || "").toLowerCase().includes(q))));
        };
        const showDetail = (o) => {
            const el = $("order-detail");
            if (!el) return;
            if (!o) { el.innerHTML = emptyBox("box", "Заказ не выбран", "Выберите заказ в списке"); return; }
            el.innerHTML = orderDetailHtml(o);
            bindOrderActions(el, o, onBan);
        };
        const onBan = (buyer, flag) => { all.forEach((x) => { if (x.buyer === buyer) x.blacklisted = flag; }); draw(); };
        const draw = () => {
            const items = filtered();
            const q = ordersQuery.trim();
            if (!items.length) {
                listEl.innerHTML = emptyBox("inbox", q ? "Ничего не нашлось" : "Здесь пусто", q ? "Попробуйте другой запрос" : "Заказов с таким статусом нет");
                showDetail(null);
                return;
            }
            if (desk) {
                if (!items.find((o) => o.id === selectedOrderId)) selectedOrderId = items[0].id;
                listEl.innerHTML = orderTable(items, selectedOrderId);
                listEl.querySelectorAll("tr[data-order]").forEach((tr) => tr.addEventListener("click", () => {
                    selectedOrderId = tr.dataset.order;
                    listEl.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
                    tr.classList.add("sel");
                    showDetail(all.find((o) => o.id === selectedOrderId));
                }));
                showDetail(all.find((o) => o.id === selectedOrderId));
                return;
            }
            const groups = [];
            for (const o of items) {
                const label = o.date ? dayLabel(new Date(o.date)) : "Без даты";
                const g = groups[groups.length - 1];
                if (g && g.label === label) g.items.push(o); else groups.push({ label, items: [o] });
            }
            listEl.innerHTML = groups.map((g) => `<div class="day-label">${esc(g.label)}</div><div class="list">${g.items.map(orderRow).join("")}</div>`).join("");
            listEl.querySelectorAll("[data-order]").forEach((el) => el.addEventListener("click", () => showOrderSheet(all.find((o) => o.id === el.dataset.order), onBan)));
        };
        draw();

        $view.querySelectorAll("[data-f]").forEach((c) => c.addEventListener("click", () => {
            ordersFilter = c.dataset.f; haptic();
            $view.querySelectorAll("[data-f]").forEach((x) => x.classList.toggle("active", x === c));
            draw();
        }));
        $("q").addEventListener("input", (e) => {
            ordersQuery = e.target.value;
            const top = $("top-q");
            if (top) top.value = ordersQuery;
            draw();
        });
        $("reload").addEventListener("click", () => { haptic(); renderOrders(null, alive, true); });
    }

    // ---------- Плагины ----------
    // ---------- Где взять плагины ----------
    // Ссылку на свой магазин меняйте здесь (url и handle).
    const SHOPS = [
        { id: "my", ic: "star", tint: "brand", title: "Мой магазин", sub: "Плагины для Cardinal+ с интерфейсом", url: "https://t.me/sqeyeshopbot", handle: "@sqeyeshopbot" },
        { id: "fpc", ic: "puzzle", tint: "blue", title: "Магазин Cardinal", sub: "Официальный канал с плагинами FunPay Cardinal", url: "https://t.me/fpc_plugins", handle: "@fpc_plugins" },
    ];
    // t.me внутри Telegram открываем сразу в Telegram, а не через браузер
    const openTgLink = (url) => { if (inTelegram && tg.openTelegramLink) tg.openTelegramLink(url); else openLink(url); };
    const shopsHtml = () => `${sectionHead("Где взять плагины")}<div class="shops">${SHOPS.map((x) => `
        <button class="shop shop-${x.id}" data-shop="${esc(x.url)}">
            <div class="ic tint-${x.tint}">${icon(x.ic)}</div>
            <div class="body"><div class="t">${esc(x.title)}</div><div class="s">${esc(x.sub)}</div></div>
            <span class="go"><span class="h">${esc(x.handle)}</span>${icon("external")}</span></button>`).join("")}</div>`;
    function bindShops() {
        $view.querySelectorAll("[data-shop]").forEach((b) => b.addEventListener("click", () => { haptic(); openTgLink(b.dataset.shop); }));
    }

    async function renderPlugins(_, alive) {
        const desk = isDesktop();
        paint(pageHead("Плагины") + (desk ? `<div class="p-grid">${sk(170, 0)}${sk(170, 0)}${sk(170, 0)}</div>` : `<div class="summary">${sk(64, 0)}${sk(64, 0)}</div>` + sk(76 * 3)));
        let d;
        try { d = await api("/api/plugins"); } catch (e) { if (alive()) paint(pageHead("Плагины") + errorBox(e)); return; }
        if (!alive()) return;

        if (!d.plugins.length) {
            paint(pageHead("Плагины") + emptyBox("puzzle", "Плагинов пока нет", "Установите плагин из файла .py — он заработает сразу, без перезапуска Cardinal")
                + `<div style="display:flex;justify-content:center;margin-top:-26px">${installBtn()}</div>` + shopsHtml());
            bindInstall();
            bindShops();
            return;
        }
        const enabled = d.plugins.filter((p) => p.enabled).length;
        const withUi = d.plugins.filter((p) => p.has_ui).length;
        const sub = `${d.plugins.length} ${plural(d.plugins.length, "плагин", "плагина", "плагинов")} · включено ${enabled} · с интерфейсом ${withUi}`;
        const note = `<div class="note">Плагины с меткой <b>UI</b> настраиваются прямо здесь. Остальные — через бота, как в обычном Cardinal.</div>`;

        if (desk) {
            paint(`${pageHead("Плагины", sub, installBtn())}
                <div class="p-grid">${d.plugins.map((p) => `
                    <div class="p-card ${p.enabled ? "" : "off"}" data-uuid="${esc(p.uuid)}">
                        <div class="top">
                            <div class="p-icon">${esc(p.icon)}</div>
                            <div style="flex:1;min-width:0"><div class="name">${esc(p.name)}${p.has_ui ? `<span class="badge ui plain">UI</span>` : ""}${warnBadge(p)}${pendBadge(p)}${licBadge(p)}</div><div class="ver">v${esc(p.version)} · ${credLink(p.credits)}</div></div>
                            <span data-stop>${sw(`data-toggle="${esc(p.uuid)}"`, p.enabled)}</span>
                        </div>
                        <div class="desc">${esc(p.description || "Без описания")}</div>
                        <div class="foot"><span>${p.has_ui ? "Настройки в приложении" : p.has_tg_settings ? "Настройки в боте" : "Без настроек"}</span><span style="color:var(--brand);font-weight:600;display:inline-flex;align-items:center">Открыть${icon("chevron")}</span></div>
                    </div>`).join("")}</div>${note}${shopsHtml()}`);
        } else {
            paint(`${pageHead("Плагины", `${d.plugins.length} ${plural(d.plugins.length, "плагин", "плагина", "плагинов")} установлено`, installBtn(true))}
                <div class="summary">
                    <div class="stat"><div class="ic tint-green">${icon("check")}</div><div><div class="v tnum" id="cnt-on">${enabled}</div><div class="l">Включено</div></div></div>
                    <div class="stat"><div class="ic tint-brand">${icon("sparkle")}</div><div><div class="v tnum">${withUi}</div><div class="l">С UI</div></div></div>
                </div>
                <div class="list">${d.plugins.map((p) => `
                    <div class="plugin-card clickable item ${p.enabled ? "" : "off"}" data-uuid="${esc(p.uuid)}" role="button">
                        <div class="p-icon">${esc(p.icon)}</div>
                        <div class="body">
                            <div class="t"><span class="txt">${esc(p.name)}</span>${p.has_ui ? `<span class="badge ui plain">UI</span>` : ""}${warnBadge(p)}${pendBadge(p)}${licBadge(p)}</div>
                            <div class="s">${esc(p.description || `Версия ${p.version}`)}</div>
                        </div>
                        <span data-stop>${sw(`data-toggle="${esc(p.uuid)}"`, p.enabled)}</span>
                    </div>`).join("")}</div>${note}${shopsHtml()}`);
        }

        bindInstall();
        bindShops();
        bindTgLinks($view);
        $view.querySelectorAll("[data-uuid]").forEach((el) => el.addEventListener("click", (e) => {
            if (e.target.closest("[data-stop]")) return;
            haptic();
            push({ type: "plugin", uuid: el.dataset.uuid });
        }));
        $view.querySelectorAll("[data-toggle]").forEach((inp) => inp.addEventListener("change", async () => {
            await togglePlugin(inp.dataset.toggle, inp);
            inp.closest("[data-uuid]").classList.toggle("off", !inp.checked);
            const c = $("cnt-on");
            if (c) c.textContent = $view.querySelectorAll("[data-toggle]:checked").length;
        }));
    }

    // ---------- Установка плагина из файла ----------
    const installBtn = (compact = false) => `<button class="btn-sm primary" id="pl-install">${icon("upload")}<span>${compact ? "Установить" : "Установить плагин"}</span></button>`;

    function pickPyFile(cb) {
        haptic();
        const inp = document.createElement("input");
        inp.type = "file";
        inp.accept = ".py,text/x-python,text/plain";
        inp.style.display = "none";
        document.body.append(inp);
        inp.addEventListener("change", () => { const f = inp.files && inp.files[0]; inp.remove(); if (f) cb(f); });
        inp.click();
    }
    function bindInstall() {
        const b = $("pl-install");
        if (b) b.addEventListener("click", () => pickPyFile((f) => startInstall(f)));
    }

    // Обновление: на сколько меняется версия и что это значит
    function versionDiff(info) {
        const note = {
            newer: ["ok", "Новая версия. Старая сохранится — если что-то пойдёт не так, её можно вернуть кнопкой «Прошлые версии»."],
            same: ["warn", "Версия в файле та же, что сейчас. Если вы меняли плагин — проверьте строку VERSION в файле или что выбран новый файл."],
            older: ["warn", "В файле более старая версия — это откат. Текущая версия тоже сохранится."],
        }[info.version_cmp] || ["ok", "Старая версия сохранится — её можно вернуть кнопкой «Прошлые версии»."];
        return `<div class="ver-diff"><div><div class="k">Сейчас</div><div class="v">v${esc(info.current_version)}</div></div>
                <span class="arr">${icon("chevron")}</span><div><div class="k">${info.version_cmp === "older" ? "Откат на" : "Станет"}</div><div class="v ${info.version_cmp === "newer" ? "up" : ""}">v${esc(info.version)}</div></div></div>
            <div class="inst-checks" style="margin-bottom:12px"><div class="chk ${note[0]}">${icon(note[0] === "ok" ? "check" : "alert")}<span>${esc(note[1])}${info.pending_version ? ` Уже ждёт перезапуска: v${esc(info.pending_version)}.` : ""} Новая версия заработает после перезапуска Cardinal.</span></div></div>`;
    }

    async function startInstall(file, expect = null) {
        const sh = openSheet(`<div class="detail" id="inst">
            <div class="head"><div class="ic tint-brand">${icon(expect ? "refresh" : "upload")}</div><div style="flex:1;min-width:0"><div class="title">${expect ? `Обновление «${esc(expect.name)}»` : "Установка плагина"}</div><div class="sub">${esc(file.name)}</div></div></div>
            ${sk(120)}${sk(58)}</div>`);
        const box = sh.querySelector("#inst");
        const fail = (msg) => {
            box.innerHTML = box.querySelector(".head").outerHTML + errorBox({ message: msg })
                + `<div style="margin-top:14px"><button class="btn secondary" id="inst-close">Закрыть</button></div>`;
            box.querySelector("#inst-close").addEventListener("click", () => closeSheet());
            notify("error");
        };
        if (!/\.py$/i.test(file.name)) return fail("Нужен файл плагина с расширением .py");
        if (file.size > 700 * 1024) return fail("Файл слишком большой (больше 700 КБ).");
        let source, info;
        try { source = await file.text(); } catch (e) { return fail("Не удалось прочитать файл."); }
        const expect_uuid = expect ? expect.uuid : undefined;
        try { info = await api("/api/plugins/inspect", { method: "POST", body: { filename: file.name, source, expect_uuid } }); }
        catch (e) { return fail(e.message); }
        if (!document.body.contains(sh)) return;

        const danger = info.checks.some((c) => c.level === "danger");
        const checks = info.checks.length
            ? `<div class="inst-checks">${info.checks.map((c) => `<div class="chk ${c.level}">${icon(c.level === "info" ? "sparkle" : "alert")}<span>${esc(c.text)}</span></div>`).join("")}</div>`
            : `<div class="inst-checks"><div class="chk ok">${icon("shield")}<span>Ничего подозрительного в коде не нашлось.</span></div></div>`;
        box.innerHTML = `
            <div class="head"><div class="ic tint-brand">${icon("puzzle")}</div><div style="flex:1;min-width:0"><div class="title">${esc(info.name)}${info.has_ui ? `<span class="badge ui plain" style="margin-left:6px;vertical-align:3px">UI</span>` : ""}</div><div class="sub">v${esc(info.version)}${info.credits ? ` · ${esc(info.credits)}` : ""}</div></div></div>
            ${info.update ? (expect ? versionDiff(info) : `<div class="warn-box" style="margin-top:0">${icon("refresh")}<div><p>Этот плагин уже установлен (v${esc(info.current_version)} → v${esc(info.version)}). Файл заменится новым, старая версия сохранится — её можно вернуть на странице плагина. Обновление заработает после перезапуска Cardinal.</p></div></div>`) : ""}
            ${info.description ? `<div class="plugin-desc" style="margin-bottom:12px">${esc(info.description)}</div>` : ""}
            ${sectionHead("Проверка кода")}
            ${checks}
            <div class="note" style="margin:10px 4px 14px">Плагин получает полный доступ к аккаунту FunPay и к компьютеру, на котором запущен Cardinal. Проверка ищет только явные признаки и не гарантирует безопасность. Ставьте плагины от тех, кому доверяете.</div>
            ${danger ? `<label class="trust"><input type="checkbox" id="inst-trust"><span>Я понимаю риск и доверяю автору плагина</span></label>` : ""}
            <button class="btn" id="inst-go" ${danger ? "disabled" : ""}>${icon(info.update ? "refresh" : "upload")}<span>${info.update ? "Обновить" : "Установить"}</span></button>
            <button class="btn secondary" id="inst-cancel">Отмена</button>`;
        const go = box.querySelector("#inst-go");
        const trust = box.querySelector("#inst-trust");
        if (trust) trust.addEventListener("change", () => { go.disabled = !trust.checked; haptic(); });
        box.querySelector("#inst-cancel").addEventListener("click", () => closeSheet());
        go.addEventListener("click", async () => {
            haptic("medium");
            go.disabled = true;
            go.querySelector("span").textContent = info.update ? "Обновляю…" : "Устанавливаю…";
            let r;
            try { r = await api("/api/plugins/install", { method: "POST", body: { filename: file.name, source, expect_uuid } }); }
            catch (e) { go.disabled = false; go.querySelector("span").textContent = "Попробовать ещё раз"; toast(e.message, "err"); notify("error"); return; }
            notify("success");
            if (r.restart_required) return askRestart(box, r);
            closeSheet();
            toast(`«${r.name}» установлен и уже работает`);
            if (stack.length === 0 && currentTab === "plugins") render(true);
        });
    }

    function askRestart(box, r) {
        box.innerHTML = `
            <div class="head"><div class="ic tint-green">${icon("check")}</div><div style="flex:1;min-width:0"><div class="title">Обновление сохранено</div><div class="sub">${esc(r.name)} v${esc(r.version)}</div></div></div>
            <div class="plugin-desc" style="margin-bottom:14px">Чтобы новая версия заработала, Cardinal нужно перезапустить. Это займёт около 30 секунд.<br><br>После перезапуска у приложения будет новый адрес: ${inTelegram ? "закройте его и откройте заново кнопкой в боте." : "получите новую ссылку командой <code>/web</code> в боте."}</div>
            <button class="btn" id="rs-go">${icon("refresh")}<span>Перезапустить сейчас</span></button>
            <button class="btn secondary" id="rs-later">Позже</button>`;
        box.querySelector("#rs-later").addEventListener("click", () => {
            closeSheet();
            toast("Обновление заработает после перезапуска Cardinal");
            if (stack.length === 0 ? currentTab === "plugins" : stack[stack.length - 1].type === "plugin") render(true);  // показать плашку «ждёт перезапуска»
        });
        box.querySelector("#rs-go").addEventListener("click", async () => {
            haptic("medium");
            try { await api("/api/restart", { method: "POST", body: {} }); }
            catch (e) { toast(e.message, "err"); notify("error"); return; }
            box.innerHTML = `<div class="empty" style="padding:28px 12px 12px"><div class="e spin">${icon("refresh")}</div><div class="h">Cardinal перезапускается</div>${inTelegram
                ? "Через полминуты откройте приложение заново кнопкой в боте."
                : "Через полминуты отправьте боту <code>/web</code> и войдите по новой ссылке."}</div>
                ${inTelegram ? `<button class="btn" id="rs-close">Закрыть приложение</button>` : ""}`;
            const c = box.querySelector("#rs-close");
            if (c) c.addEventListener("click", () => { try { tg.close(); } catch (e) {} });
        });
    }

    // ---------- прошлые версии плагина (копии, которые сохраняет обновление) ----------
    async function loadBackups(p, alive) {
        let list = [];
        try { list = (await api(`/api/plugins/${p.uuid}/backups`)).backups; } catch (e) { return; }
        const b = $("pl-backups");
        if (!alive() || !b || !list.length) return;
        b.hidden = false;
        const s = $("pl-backups-s");
        if (s) s.textContent = `${list.length} ${plural(list.length, "копия", "копии", "копий")} · последняя v${list[0].version}`;
        b.addEventListener("click", () => backupsSheet(p, list));
    }
    function backupsSheet(p, list) {
        haptic();
        const sh = openSheet(`<div class="detail">
            <div class="head"><div class="ic tint-gray">${icon("history")}</div><div style="flex:1;min-width:0"><div class="title">Прошлые версии</div><div class="sub">${esc(p.name)} · работает v${esc(p.version)}${p.pending_update ? `, после перезапуска — v${esc(p.pending_update.version)}` : ""}</div></div></div>
            <div class="list">${list.map((b, i) => `<div class="item"><div class="ic tint-gray">${icon("restore")}</div>
                <div class="body"><div class="t">v${esc(b.version)}</div><div class="s">сохранена ${new Date(b.time * 1000).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</div></div>
                <button class="btn-sm" data-rb="${i}">Вернуть</button></div>`).join("")}</div>
            <div class="note">Копия появляется при каждом обновлении. Если вернуть старую версию, текущая тоже сохранится — передумаете, вернёте и её. Работать будет после перезапуска Cardinal.</div></div>`);
        sh.querySelectorAll("[data-rb]").forEach((btn) => btn.addEventListener("click", async () => {
            const b = list[+btn.dataset.rb];
            if (!(await confirmDialog(`Вернуть «${p.name}» к версии v${b.version}?\n\nТекущая версия v${p.version} сохранится. Заработает после перезапуска Cardinal.`))) return;
            btn.disabled = true;
            try {
                const r = await api(`/api/plugins/${p.uuid}/rollback`, { method: "POST", body: { file: b.file } });
                notify("success");
                askRestart(sh.querySelector(".detail"), r);
            } catch (e) { btn.disabled = false; toast(e.message, "err"); notify("error"); }
        }));
    }

    async function togglePlugin(uuid, inp) {
        haptic("medium");
        inp.disabled = true;
        try {
            const r = await api(`/api/plugins/${uuid}/toggle`, { method: "POST", body: { enabled: inp.checked } });
            inp.checked = r.enabled;
            toast(r.enabled ? "Плагин включён" : "Плагин выключен");
        } catch (e) { inp.checked = !inp.checked; toast(e.message, "err"); notify("error"); }
        finally { inp.disabled = false; }
    }

    function fieldHtml(f, value) {
        const id = `f_${f.key}`;
        const hint = f.hint ? `<div class="hint">${esc(f.hint)}</div>` : "";
        switch (f.type) {
            case "section":
                return `</div>${sectionHead(f.label)}<div class="list">`;
            case "toggle":
                return `<div class="field row"><div class="grow"><label for="${id}">${esc(f.label)}</label>${hint}</div>${sw(`id="${id}" data-key="${esc(f.key)}"`, value)}</div>`;
            case "textarea":
                return `<div class="field"><label for="${id}">${esc(f.label)}</label>
                    <textarea id="${id}" data-key="${esc(f.key)}" placeholder="${esc(f.placeholder || "")}">${esc(value)}</textarea>${hint}</div>`;
            case "number":
                return `<div class="field"><label for="${id}">${esc(f.label)}</label>
                    <input type="number" inputmode="decimal" id="${id}" data-key="${esc(f.key)}" value="${esc(value)}"
                        ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""}>${hint}</div>`;
            case "select":
                return `<div class="field"><label for="${id}">${esc(f.label)}</label>
                    <select id="${id}" data-key="${esc(f.key)}">${(f.options || []).map(([v, l]) =>
                        `<option value="${esc(v)}" ${String(v) === String(value) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>${hint}</div>`;
            default:
                return `<div class="field"><label for="${id}">${esc(f.label)}</label>
                    <input type="text" id="${id}" data-key="${esc(f.key)}" value="${esc(value)}" placeholder="${esc(f.placeholder || "")}">${hint}</div>`;
        }
    }

    async function renderPlugin(screen, alive) {
        paint(`<div class="skeleton" style="width:76px;height:76px;border-radius:24px;margin:6px auto 14px"></div>` + sk(22, 26, 8) + sk(58) + sk(220));
        let p;
        try { p = await api(`/api/plugins/${screen.uuid}`); } catch (e) { if (alive()) paint(errorBox(e)); return; }
        if (!alive()) return;
        const desk = isDesktop();

        const settings = p.settings.length
            ? sectionHead("Настройки") + `<div class="list">${p.settings.map((f) => fieldHtml(f, p.values[f.key])).join("")}</div>` : "";
        const tgOnly = !p.has_ui && p.has_tg_settings
            ? `<div class="list" style="margin-top:10px"><div class="item">
                    <div class="ic tint-blue">${icon("tg")}</div>
                    <div class="body"><div class="t">Настройки в боте</div><div class="s">/menu → Плагины → ${esc(p.name)}</div></div></div></div>` : "";
        const lic = p.license;
        const licTitle = lic ? (lic.dev ? "Копия разработчика" : lic.ok ? "Лицензия действует" : "Лицензия не подходит") : "";
        const buyBtn = lic && !lic.ok && lic.shop ? `<button class="btn-sm primary" data-tg="https://t.me/${esc(lic.shop.replace("@", ""))}">${icon("lock")}<span>Купить в ${esc(lic.shop)}</span></button>` : "";
        const buyShort = lic && !lic.ok && lic.shop ? `<button class="btn-sm primary" data-tg="https://t.me/${esc(lic.shop.replace("@", ""))}">Купить</button>` : "";
        const licItem = lic ? `<div class="item"><div class="ic ${lic.ok ? "tint-green" : "tint-red"}">${icon(lic.ok ? "shield" : "lock")}</div>
            <div class="body"><div class="t">${licTitle}</div><div class="s">${esc(lic.text)}</div></div>${buyShort}</div>` : "";
        const licBanner = lic && !lic.ok ? `<div class="banner lic-banner"><div class="ring">${icon("lock")}</div>
            <div class="grow"><div class="t">Плагин не работает: лицензия не подходит</div><div class="s">${esc(lic.text)}. Лицензия привязана к одному аккаунту FunPay.</div></div>${buyBtn}</div>` : "";
        const pu = p.pending_update;
        const pending = pu ? `<div class="banner upd-banner"><div class="ring">${icon("refresh")}</div>
            <div class="grow"><div class="t">Новая версия v${esc(pu.version)} установлена</div><div class="s">Заработает после перезапуска Cardinal — сейчас работает v${esc(p.version)}</div></div>
            <button class="btn-sm primary" id="pl-restart">${icon("refresh")}<span>Перезапустить</span></button></div>` : "";
        const commands = Object.keys(p.commands || {}).length
            ? sectionHead("Команды бота") + `<div class="list">${Object.entries(p.commands).map(([c, h]) =>
                `<div class="item"><div class="ic tint-gray">${icon("terminal")}</div><div class="body"><div class="t">/${esc(c)}</div><div class="s">${esc(h)}</div></div></div>`).join("")}</div>` : "";
        const hero = `
            <div class="plugin-hero">
                <div class="p-icon lg">${esc(p.icon)}</div>
                <div class="name">${esc(p.name)}</div>
                <div class="meta">Версия ${esc(p.version)} · ${credLink(p.credits)}</div>
            </div>
            ${pending}
            <div class="list" style="margin-top:20px">
                <div class="item">
                    <div class="ic ${p.enabled ? "tint-green" : "tint-gray"}" id="pl-ic">${icon("check")}</div>
                    <div class="body"><div class="t">Плагин включён</div></div>
                    ${sw('id="pl-enabled"', p.enabled)}
                </div>
                ${licItem}
                <button class="item clickable" id="pl-update">
                    <div class="ic tint-blue">${icon("upload")}</div>
                    <div class="body"><div class="t">Обновить плагин</div><div class="s">Загрузить новую версию файла .py</div></div>
                    <span class="chev">${icon("chevron")}</span>
                </button>
                <button class="item clickable" id="pl-backups" hidden>
                    <div class="ic tint-gray">${icon("history")}</div>
                    <div class="body"><div class="t">Прошлые версии</div><div class="s" id="pl-backups-s">Вернуть сохранённую копию</div></div>
                    <span class="chev">${icon("chevron")}</span>
                </button>
            </div>
            ${tgOnly}`;
        // описания здесь нет: оно уже показано в списке плагинов и в окне установки
        const del = `<button class="btn danger" id="pl-delete" style="margin-top:18px">${icon("trash")}<span>Удалить плагин</span></button>`;
        const page = p.page_url ? sectionHead(p.page_title || "Страница плагина") + `<iframe class="plugin-frame" id="pl-frame" src="${esc(p.page_url)}" allow="clipboard-write"></iframe>` : "";

        if (desk) {
            // Панель: шапка плагина одной строкой, а интерфейс и настройки — на всю ширину
            const body = p.page_first ? page + settings : settings + page;
            paint(`
                <div class="panel pl-bar">
                    <button class="icon-btn sm" id="pl-back" title="Все плагины" aria-label="Все плагины">${icon("chevron", "flip")}</button>
                    <div class="p-icon">${esc(p.icon)}</div>
                    <div class="body"><div class="t">${esc(p.name)}</div><div class="s">Версия ${esc(p.version)} · ${credLink(p.credits)}${lic && lic.ok ? ` · <span class="lic-ok">${icon("shield")}${esc(lic.dev ? "копия разработчика" : lic.text)}</span>` : ""}</div></div>
                    <label class="pl-sw"><span id="pl-state">${p.enabled ? "Включён" : "Выключен"}</span>${sw('id="pl-enabled"', p.enabled)}</label>
                    <span class="sep"></span>
                    <button class="btn-sm" id="pl-backups" hidden title="Вернуть сохранённую копию">${icon("history")}<span>Прошлые версии</span></button>
                    <button class="btn-sm" id="pl-update" title="Загрузить новую версию файла .py">${icon("upload")}<span>Обновить</span></button>
                    <button class="btn-sm danger-sm" id="pl-delete">${icon("trash")}<span>Удалить</span></button>
                </div>
                ${licBanner}${pending}${warnBox(p)}${tgOnly}
                ${body || emptyBox("sliders", "Нет настроек в приложении", p.has_tg_settings ? "Настройки этого плагина открываются в боте" : "У этого плагина нет настроек")}
                ${commands}`);
            $("pl-back").querySelector("svg").style.transform = "rotate(180deg)";
            $("pl-back").addEventListener("click", back);
        } else {
            paint(hero + warnBox(p) + (p.page_first ? page + settings : settings + page) + commands + del);
        }

        $("pl-update").addEventListener("click", () => pickPyFile((f) => startInstall(f, p)));
        bindTgLinks($view);
        if ($("pl-restart")) $("pl-restart").addEventListener("click", () => {
            haptic("medium");
            const sh = openSheet(`<div class="detail" id="rs-box"></div>`);
            askRestart(sh.querySelector("#rs-box"), { name: p.name, version: pu.version });
        });
        loadBackups(p, alive);
        $("pl-delete").addEventListener("click", async () => {
            haptic("medium");
            const ok = await confirmDialog(`Удалить плагин «${p.name}»?\n\nФайл переместится в storage/plugin_backups — его можно вернуть. Настройки плагина сохранятся.`);
            if (!ok) return;
            const b = $("pl-delete");
            b.disabled = true;
            try {
                await api(`/api/plugins/${p.uuid}/delete`, { method: "POST", body: {} });
                notify("success");
                toast(`«${p.name}» удалён`);
                back();
            } catch (e) { b.disabled = false; toast(e.message, "err"); notify("error"); }
        });
        $("pl-enabled").addEventListener("change", async (e) => {
            await togglePlugin(p.uuid, e.target);
            const ic = $("pl-ic"), st = $("pl-state");
            if (ic) ic.className = `ic ${e.target.checked ? "tint-green" : "tint-gray"}`;
            if (st) st.textContent = e.target.checked ? "Включён" : "Выключен";
        });
        $view.querySelectorAll("[data-key]").forEach((el) => {
            el.addEventListener("change", async () => {
                const value = el.type === "checkbox" ? el.checked : el.value;
                try {
                    const r = await api(`/api/plugins/${p.uuid}/settings`, { method: "POST", body: { key: el.dataset.key, value } });
                    if (el.type === "checkbox") el.checked = r.value; else el.value = r.value;
                    haptic("light");
                    toast("Сохранено");
                } catch (e) {
                    toast(e.message, "err"); notify("error");
                    if (el.type === "checkbox") el.checked = !el.checked;
                }
            });
        });
        const frame = $("pl-frame");
        if (frame) {
            const fit = () => { try { frame.style.height = Math.max(120, frame.contentDocument.body.scrollHeight + 4) + "px"; } catch (e) {} };
            frame.addEventListener("load", () => {
                fit();
                try { new ResizeObserver(fit).observe(frame.contentDocument.body); } catch (e) {}
            });
        }
    }

    // ---------- Чаты ----------
    // Телефон: список чатов → переписка с шаблонами. Панель: список | переписка | карточка покупателя.
    const chatState = { list: null, unread: 0, sel: null, q: "" };
    let chatTimers = [];
    let convSeq = 0;

    // Открыть переписку со страницы плагина (Plugin.openChat в plugin-sdk.js)
    function openChatFromPlugin(id, name) {
        id = Number(id);
        if (!Number.isSafeInteger(id) || id <= 0) return;
        haptic("light");
        const known = (chatState.list || []).find((x) => x.id === id);
        const chat = known || { id, name: String(name || "Чат") };
        if (isDesktop()) {
            chatState.sel = id;
            chatState.pending = chat;
            chatState.q = "";
            setTab("chats");
        } else {
            push({ type: "chat", id, name: chat.name, avatar: chat.avatar });
        }
    }
    const stopChatTimers = () => { chatTimers.forEach(clearInterval); chatTimers = []; };

    function chatAva(c) {
        let h = 0;
        for (const ch of String(c.name || "?")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
        const [a, b] = PALETTE[h % PALETTE.length];
        const img = c.avatar ? `<img src="${esc(c.avatar)}" alt="" referrerpolicy="no-referrer" decoding="async" onerror="this.remove()">` : "";
        return `<div class="buyer ava" style="background:linear-gradient(135deg,${a},${b})">${esc((c.name || "?")[0].toUpperCase())}${img}</div>`;
    }

    // Текст сообщения: экранируем, ссылки и номера заказов делаем кликабельными
    function chatText(t) {
        let h = esc(t || "");
        h = h.replace(/\bhttps?:\/\/[^\s<]+/g, (u) => `<a data-link="${u}">${u}</a>`);
        h = h.replace(/(^|[^\w/])#([A-Z0-9]{8})\b/g, (m, pre, id) => `${pre}<a data-link="https://funpay.com/orders/${id}/">#${id}</a>`);
        return h;
    }
    document.addEventListener("click", (e) => {
        const a = e.target.closest("[data-link]");
        if (!a || !a.closest(".chat-scroll, .buyer-card, .bc-orders")) return;
        e.preventDefault();
        openLink(a.dataset.link);
    });

    function bubbleHtml(m, prev) {
        if (m.system) return `<div class="msg-sys">${chatText(m.text)}</div>`;
        const grouped = prev && !prev.system && prev.mine === m.mine && prev.author === m.author;
        const meta = (m.badge ? `<span class="msg-badge">${esc(m.badge)}</span>` : "")
            + (m.bot ? `<span class="msg-badge">бот</span>` : "")
            + (m.time ? `<span title="${esc(m.time_full || "")}">${esc(m.time)}</span>` : "");
        const body = m.image
            ? `<a class="msg-img" data-link="${esc(m.image)}"><img src="${esc(m.image)}" alt="Изображение" referrerpolicy="no-referrer" loading="lazy" decoding="async" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'msg-img-fail',textContent:'Изображение — открыть'}))"></a>`
            : `<div class="msg-text">${chatText(m.text)}</div>`;
        return `<div class="msg ${m.mine ? "mine" : "their"}${grouped ? " grouped" : ""}">
            ${!m.mine && !grouped && m.author ? `<div class="msg-author">${esc(m.author)}</div>` : ""}
            <div class="bubble">${body}${meta ? `<div class="msg-meta">${meta}</div>` : ""}</div></div>`;
    }

    // Картинка для чата → base64. Большие картинки уменьшаем и пережимаем в JPEG:
    // сервер приложения принимает запрос до 1 МБ, а FunPay всё равно показывает картинку уменьшенной.
    async function imageToBase64(file) {
        const LIMIT = 700 * 1024, MAX_SIDE = 1920;
        const toB64 = (buf) => {
            const bytes = new Uint8Array(buf);
            let s = "";
            for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            return btoa(s);
        };
        if (file.size <= LIMIT && file.type !== "image/webp") return toB64(await file.arrayBuffer());  // небольшие — как есть
        const url = URL.createObjectURL(file);
        try {
            const img = await new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => fail(new Error("Не удалось открыть картинку")); i.src = url; });
            let w = img.naturalWidth, h = img.naturalHeight;
            const k = Math.min(1, MAX_SIDE / Math.max(w, h));
            w = Math.max(1, Math.round(w * k)); h = Math.max(1, Math.round(h * k));
            for (const [scale, q] of [[1, .88], [1, .78], [.8, .75], [.6, .7], [.45, .65]]) {
                const c = document.createElement("canvas");
                c.width = Math.round(w * scale); c.height = Math.round(h * scale);
                const ctx = c.getContext("2d");
                ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);  // прозрачный фон PNG → белый, а не чёрный
                ctx.drawImage(img, 0, 0, c.width, c.height);
                const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", q));
                if (blob && blob.size <= LIMIT) return toB64(await blob.arrayBuffer());
            }
            throw new Error("Картинка слишком большая — попробуйте другую");
        } finally { URL.revokeObjectURL(url); }
    }

    const composerHtml = () => `<div class="composer">
        <button class="icon-btn tpl-btn" title="Шаблоны ответов" aria-label="Шаблоны ответов">${icon("layers")}</button>
        <button class="icon-btn img-btn" title="Отправить картинку" aria-label="Отправить картинку">${icon("image")}</button>
        <input type="file" class="img-input" accept="image/jpeg,image/png,image/gif,image/webp" hidden>
        <textarea rows="1" maxlength="2000" placeholder="Сообщение…"></textarea>
        <button class="send" title="Отправить" aria-label="Отправить">${icon("send")}</button></div>`;

    function setChatBadge(n) {
        chatState.unread = n;
        const a = $("nav-chats"); if (a) a.textContent = n || "";
        const b = $("tb-chats"); if (b) { b.textContent = n > 99 ? "99+" : n; b.classList.toggle("show", n > 0); }
    }
    async function loadChats() {
        const d = await api("/api/chats");
        chatState.list = d.chats;
        chatState.waiting = d.waiting || 0;
        setChatBadge(d.unread);
        return d;
    }
    function markListRead(id) {
        const c = chatState.list && chatState.list.find((x) => x.id === id);
        if (c && c.unread) { c.unread = false; setChatBadge(Math.max(0, chatState.unread - 1)); }
    }
    // Счётчик непрочитанных обновляется и когда открыт другой раздел
    setInterval(() => {
        if (!booted || document.hidden) return;
        const scr = stack.length ? stack[stack.length - 1].type : currentTab;
        if (scr !== "chats" && scr !== "chat") loadChats().catch(() => {});
    }, 15000);

    function filteredChats() {
        const q = chatState.q.trim().toLowerCase();
        const list = chatState.list || [];
        return q ? list.filter((c) => c.name.toLowerCase().includes(q) || (c.last_text || "").toLowerCase().includes(q)) : list;
    }
    const chatItemHtml = (c) => `
        <div class="item clickable chat-item${c.unread ? " unread" : ""}${chatState.sel === c.id && isDesktop() ? " sel" : ""}" data-chat="${c.id}" role="button">
            ${chatAva(c)}
            <div class="body"><div class="t"><span class="txt">${esc(c.name)}</span>${c.blacklisted ? `<span class="badge refunded plain">ЧС</span>` : ""}${c.waiting != null ? `<span class="badge paid plain wait-b" title="Покупатель ждёт вашего ответа">${icon("clock")}${waitLabel(c.waiting)}</span>` : ""}</div>
                <div class="s">${c.last_by_bot ? "Бот: " : ""}${esc(c.last_text || "")}</div></div>
            <div class="right"><div class="chat-time">${esc(c.time || "")}</div>${c.unread ? `<span class="dot"></span>` : ""}</div>
        </div>`;
    const noChatsHtml = () => chatState.q
        ? `<div class="empty-sm">Ничего не нашлось</div>`
        : emptyBox("chat", "Чатов пока нет", "Здесь появятся переписки с покупателями");

    /** Переписка: загрузка, опрос новых сообщений, отправка, шаблоны. */
    function mountConversation(box, chat, alive, onInfo) {
        const scroll = box.querySelector(".chat-scroll");
        const input = box.querySelector(".composer textarea");
        const sendBtn = box.querySelector(".composer .send");
        let lastId = 0, name = chat.name || "", busy = false;
        const msgs = [];
        const nearBottom = () => scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 90;
        const toBottom = () => { scroll.scrollTop = scroll.scrollHeight; };

        function append(list, force) {
            const fresh = list.filter((m) => !msgs.some((x) => x.id === m.id));
            if (!fresh.length) return;
            const stick = force || nearBottom();
            let html = "", prev = msgs[msgs.length - 1];
            for (const m of fresh) { html += bubbleHtml(m, prev); prev = m; msgs.push(m); lastId = Math.max(lastId, m.id); }
            const empty = scroll.querySelector(".chat-empty"); if (empty) empty.remove();
            scroll.insertAdjacentHTML("beforeend", html);
            scroll.querySelectorAll(".msg-img img").forEach((img) => { if (!img.dataset.b) { img.dataset.b = 1; img.addEventListener("load", () => stick && toBottom(), { once: true }); } });
            if (stick) toBottom();
        }
        async function load() {
            try {
                const r = await api(`/api/chats/${chat.id}?read=1`);
                if (!alive()) return;
                name = r.chat.name || name;
                onInfo && onInfo(r.chat);
                scroll.innerHTML = r.messages.length ? "" : `<div class="chat-empty">Сообщений пока нет</div>`;
                append(r.messages, true);
                lastId = Math.max(lastId, r.last_id || 0);
                markListRead(chat.id);
            } catch (e) { if (alive()) scroll.innerHTML = errorBox(e); }
        }
        async function poll() {
            if (!alive() || document.hidden || busy) return;
            busy = true;
            try {
                const r = await api(`/api/chats/${chat.id}?since=${lastId}&read=1`);
                if (alive() && r.messages.length) { append(r.messages); markListRead(chat.id); }
            } catch (e) {} finally { busy = false; }
        }
        const autosize = () => {
            input.style.height = "auto";
            input.style.height = Math.min(140, input.scrollHeight + 2) + "px";
            input.style.overflowY = input.scrollHeight > 140 ? "auto" : "hidden";
        };
        async function send() {
            const text = input.value.trim();
            if (!text || sendBtn.disabled) return;
            sendBtn.disabled = true;
            haptic("light");
            try {
                const r = await api(`/api/chats/${chat.id}/send`, { method: "POST", body: { text } });
                input.value = ""; autosize();
                append(r.messages, true);
                if (!r.messages.length) setTimeout(poll, 1500);
            } catch (e) { toast(e.message, "err"); notify("error"); }
            finally { sendBtn.disabled = false; if (isDesktop()) input.focus(); }
        }
        input.addEventListener("input", autosize);
        input.addEventListener("keydown", (e) => {
            // В Панели Enter отправляет, Shift+Enter — новая строка. На телефоне Enter — всегда новая строка.
            if (e.key === "Enter" && !e.shiftKey && isDesktop()) { e.preventDefault(); send(); }
        });
        sendBtn.addEventListener("click", send);
        box.querySelector(".tpl-btn").addEventListener("click", () => openTemplates(name, (text) => {
            input.value = input.value.trim() ? `${input.value.trim()} ${text}` : text;
            autosize(); input.focus();
        }));

        // ----- картинки: кнопка; в Панели ещё Ctrl+V и перетаскивание -----
        const fileInput = box.querySelector(".img-input");
        box.querySelector(".img-btn").addEventListener("click", () => { haptic("light"); fileInput.click(); });
        fileInput.addEventListener("change", () => { const f = fileInput.files[0]; fileInput.value = ""; if (f) previewImage(f); });
        function previewImage(file) {
            if (!/^image\/(jpeg|png|gif|webp)$/.test(file.type)) return toast("Можно отправить JPG, PNG, GIF или WEBP", "err");
            const url = URL.createObjectURL(file);
            const sh = openSheet(`<div class="head"><div><div class="title">Отправить картинку?</div><div class="sub">${esc(name || "Покупатель")} получит её в чате FunPay</div></div></div>
                <div class="img-preview"><img src="${url}" alt=""></div>
                <div class="img-acts"><button class="btn secondary" id="ip-cancel">Отмена</button><button class="btn" id="ip-send">${icon("send")}<span>Отправить</span></button></div>`);
            const done = () => { closeSheet(); setTimeout(() => URL.revokeObjectURL(url), 400); };
            sh.querySelector("#ip-cancel").addEventListener("click", done);
            sh.querySelector("#ip-send").addEventListener("click", () => { done(); sendImage(file); });
        }
        async function sendImage(file) {
            const temp = document.createElement("div");
            temp.className = "msg mine img-sending";
            temp.innerHTML = `<div class="bubble"><div class="msg-text">${icon("image")} Отправляю картинку…</div></div>`;
            scroll.append(temp); toBottom();
            try {
                const image = await imageToBase64(file);
                const r = await api(`/api/chats/${chat.id}/image`, { method: "POST", body: { image } });
                temp.remove();
                append(r.messages, true);
                if (!r.messages.length) setTimeout(poll, 1500);
                haptic("light");
            } catch (e) { temp.remove(); toast(e.message, "err"); notify("error"); }
        }
        if (isDesktop()) {
            input.addEventListener("paste", (e) => {
                const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
                if (!item) return;
                e.preventDefault();
                const f = item.getAsFile();
                if (f) previewImage(f);
            });
            box.addEventListener("dragover", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { e.preventDefault(); box.classList.add("img-drop"); } });
            box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("img-drop"); });
            box.addEventListener("drop", (e) => {
                box.classList.remove("img-drop");
                const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith("image/"));
                if (!f) return;
                e.preventDefault();
                previewImage(f);
            });
        }
        load();
        chatTimers.push(setInterval(poll, 3000));
        if (isDesktop()) {
            input.placeholder = "Сообщение… (Enter — отправить)";
            input.title = "Enter — отправить, Shift+Enter — новая строка";
            setTimeout(() => input.focus(), 50);
        }
    }

    async function openTemplates(name, onPick) {
        const desk = isDesktop();
        const head = `<div class="head"><div class="ic tint-blue">${icon("layers")}</div><div style="flex:1;min-width:0"><div class="title">Шаблоны ответов</div><div class="sub">Общие с ботом Cardinal · $username — ник покупателя</div></div></div>`;
        const sh = openSheet(`<div class="detail" id="tpl">${head}${sk(58)}${sk(58)}</div>`);
        const box = sh.querySelector("#tpl");
        const draw = (items) => {
            box.innerHTML = head + (items.length
                ? `<div class="list tpl-list">${items.map((t, i) => `
                    <div class="item clickable" data-pick="${i}" role="button"><div class="body"><div class="tpl-text">${esc(t)}</div></div>
                    ${desk ? `<button class="tpl-del" data-del="${i}" title="Удалить шаблон">${icon("trash")}</button>` : ""}</div>`).join("")}</div>`
                : `<div class="empty-sm">Шаблонов пока нет.${desk ? " Добавьте первый ниже." : " Добавить их можно в Панели или в боте Cardinal."}</div>`)
                + (desk ? `<div class="tpl-add"><textarea id="tpl-new" maxlength="2000" placeholder="Новый шаблон, например: Здравствуйте, $username! Сейчас всё проверю."></textarea>
                    <button class="btn-sm primary" id="tpl-save">${icon("check")}<span>Добавить шаблон</span></button></div>` : "");
            box.querySelectorAll("[data-pick]").forEach((el) => el.addEventListener("click", (e) => {
                if (e.target.closest("[data-del]")) return;
                haptic("light");
                onPick(items[+el.dataset.pick].replace(/\$username/g, name || ""));
                closeSheet();
            }));
            box.querySelectorAll("[data-del]").forEach((el) => el.addEventListener("click", async () => {
                if (!(await confirmDialog("Удалить этот шаблон? Он пропадёт и в боте."))) return;
                try { draw((await api("/api/chats/templates", { method: "POST", body: { action: "delete", index: +el.dataset.del } })).templates); toast("Шаблон удалён"); }
                catch (err) { toast(err.message, "err"); }
            }));
            const save = box.querySelector("#tpl-save");
            if (save) save.addEventListener("click", async () => {
                const text = box.querySelector("#tpl-new").value;
                try { draw((await api("/api/chats/templates", { method: "POST", body: { action: "add", text } })).templates); toast("Шаблон добавлен"); }
                catch (err) { toast(err.message, "err"); }
            });
        };
        try { draw((await api("/api/chats/templates")).templates); }
        catch (e) { box.innerHTML = head + errorBox(e); }
    }

    // ----- телефон: список чатов -----
    async function renderChats(screen, alive) {
        if (isDesktop()) return renderChatsDesk(screen, alive);
        paint(pageHead("Чаты") + sk(46) + sk(66 * 5));
        try { await loadChats(); } catch (e) { if (alive()) paint(pageHead("Чаты") + errorBox(e)); return; }
        if (!alive()) return;
        const sub = () => (chatState.unread ? `${chatState.unread} ${plural(chatState.unread, "непрочитанный", "непрочитанных", "непрочитанных")}` : "Все прочитаны")
            + (chatState.waiting ? ` · ждут ответа: ${chatState.waiting}` : "");
        paint(`${pageHead("Чаты", `<span id="ch-sub">${sub()}</span>`)}
            <label class="search">${icon("search")}<input id="ch-q" type="search" placeholder="Ник или текст сообщения" autocomplete="off" value="${esc(chatState.q)}"></label>
            <div id="ch-list"></div>`);
        const drawList = () => {
            const items = filteredChats();
            $("ch-list").innerHTML = items.length ? `<div class="list">${items.map(chatItemHtml).join("")}</div>` : noChatsHtml();
            const s = $("ch-sub"); if (s) s.textContent = sub();
        };
        drawList();
        $("ch-q").addEventListener("input", (e) => { chatState.q = e.target.value; drawList(); });
        $("ch-list").addEventListener("click", (e) => {
            const el = e.target.closest("[data-chat]");
            if (!el) return;
            haptic();
            const c = chatState.list.find((x) => x.id === +el.dataset.chat);
            if (c) push({ type: "chat", id: c.id, name: c.name, avatar: c.avatar });
        });
        chatTimers.push(setInterval(async () => {
            if (!alive() || document.hidden) return;
            try { await loadChats(); if (alive()) drawList(); } catch (e) {}
        }, 5000));
    }

    // ----- телефон: переписка -----
    function renderChat(screen, alive) {
        document.body.classList.add("chat-open");
        paint(`<div class="chat-m">
            <div class="chat-m-head">
                ${inTelegram ? "" : `<button class="icon-btn" id="cm-back" aria-label="Назад">${icon("chevron", "flip")}</button>`}
                ${chatAva(screen)}
                <div class="body"><div class="t">${esc(screen.name || "Чат")}</div><div class="s" id="cm-sub">Переписка на FunPay</div></div>
                <button class="icon-btn" id="cm-open" title="Открыть на FunPay" aria-label="Открыть на FunPay">${icon("external")}</button>
            </div>
            <div class="chat-scroll">${sk(44, 8, 16)}${sk(44, 8, 16)}${sk(44, 8, 16)}</div>
            ${composerHtml()}
        </div>`);
        const b = $("cm-back"); if (b) b.addEventListener("click", back);
        $("cm-open").addEventListener("click", () => openLink(`https://funpay.com/chat/?node=${screen.id}`));
        mountConversation($view.querySelector(".chat-m"), screen, alive, (info) => {
            const s = $("cm-sub"); if (s && info.blacklisted) s.textContent = "В чёрном списке";
        });
    }

    // ----- Панель: список | переписка | покупатель -----
    function fitChatDesk() {
        const el = $("cd");
        if (!el) return;
        el.style.height = Math.max(440, innerHeight - el.getBoundingClientRect().top - 40) + "px";
    }
    window.addEventListener("resize", fitChatDesk);

    async function renderChatsDesk(screen, alive) {
        paint(`<div class="chat-desk" id="cd">
            <div class="cd-list">
                <div class="cd-top"><div class="cd-title">Чаты <span id="cd-unread"></span></div>
                    <label class="search">${icon("search")}<input id="cd-q" type="search" placeholder="Ник или текст · Enter — по всей переписке" autocomplete="off" value="${esc(chatState.q)}"></label></div>
                <div class="cd-items" id="cd-items">${sk(58, 6)}${sk(58, 6)}${sk(58, 6)}${sk(58, 6)}</div>
            </div>
            <div class="cd-conv" id="cd-conv">${emptyBox("chat", "Выберите чат", "Слева — все переписки с покупателями")}</div>
            <div class="cd-side" id="cd-side"></div>
        </div>`);
        fitChatDesk();
        const drawList = () => {
            if (chatState.deep) return drawDeep();
            const items = filteredChats();
            const box = $("cd-items");
            if (!box) return;
            const top = box.scrollTop;
            box.innerHTML = items.length ? items.map(chatItemHtml).join("") : noChatsHtml();
            box.scrollTop = top;
            const u = $("cd-unread"); if (u) u.textContent = chatState.unread ? chatState.unread : "";
        };
        try { await loadChats(); } catch (e) { if (alive()) $("cd-items").innerHTML = errorBox(e); return; }
        if (!alive()) return;
        drawList();
        // выбранный раньше чат (или открытый со страницы плагина) сразу показываем справа
        const pending = chatState.pending && chatState.pending.id === chatState.sel ? chatState.pending : null;
        chatState.pending = null;
        const pre = chatState.sel && (chatState.list.find((x) => x.id === chatState.sel) || pending);
        if (pre) openDeskChat(pre);
        $("cd-q").addEventListener("input", (e) => { chatState.q = e.target.value; chatState.deep = null; drawList(); });
        // поиск по всей переписке (архив Cardinal+)
        const runDeep = async (q) => {
            const box = $("cd-items");
            box.innerHTML = sk(58, 6) + sk(58, 6) + sk(58, 6);
            try { chatState.deep = { ...(await api(`/api/chats/search?q=${encodeURIComponent(q)}`)), q }; }
            catch (err) { chatState.deep = null; toast(err.message, "err"); drawList(); return; }
            if (alive()) drawDeep();
        };
        $("cd-q").addEventListener("keydown", (e) => {
            if (e.key !== "Enter") return;
            const q = e.target.value.trim();
            if (q.length < 2) { toast("Введите хотя бы 2 символа", "err"); return; }
            runDeep(q);
        });
        function drawDeep() {
            const d = chatState.deep, box = $("cd-items");
            if (!d || !box) return;
            const rx = new RegExp(esc(d.q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
            const mark = (t) => esc(t).replace(rx, (m) => `<mark>${m}</mark>`);
            const snip = (t) => { const i = t.toLowerCase().indexOf(d.q.toLowerCase()), s = Math.max(0, i - 50); return (s ? "…" : "") + t.slice(s, s + 170) + (t.length > s + 170 ? "…" : ""); };
            const found = d.results.length + d.chats.length + d.orders.length;
            box.innerHTML = `<div class="sr-head"><button class="link-btn" id="sr-back">${icon("chevron", "flip")}Все чаты</button><span class="muted">${found ? "" : "ничего не нашлось"}</span></div>
                ${d.orders.map((o) => `<div class="item sr-item" data-deep-chat="${esc(o.chat_id || "")}" data-deep-name="${esc(o.buyer)}"><div class="ic tint-amber">${icon("box")}</div>
                    <div class="body"><div class="t"><span class="txt">Заказ #${esc(o.id)} · ${esc(o.buyer)}</span></div><div class="s">${esc(o.description || "")}</div></div></div>`).join("")}
                ${d.chats.length ? `<div class="sr-sub">Чаты · ${d.chats.length}</div>` : ""}
                ${d.chats.map((c) => `<div class="item sr-item" data-deep-chat="${c.id}" data-deep-name="${esc(c.name)}">${chatAva(c)}<div class="body"><div class="t"><span class="txt">${mark(c.name)}</span></div><div class="s">${esc(c.last_text || "")}</div></div></div>`).join("")}
                ${d.results.length ? `<div class="sr-sub">В переписке · ${d.results.length}${d.results.length >= 60 ? "+" : ""}</div>` : ""}
                ${d.results.map((r) => `<div class="item sr-item" data-deep-chat="${r.chat_id}" data-deep-name="${esc(r.chat_name || "")}"><div class="body">
                    <div class="t"><span class="txt">${esc(r.chat_name || "Чат")}</span><span class="sr-when">${esc(r.when || tsDay(r.ts))}</span></div>
                    <div class="s sr-snip">${r.mine ? "Вы: " : ""}${mark(snip(r.text))}</div></div></div>`).join("")}
                <div class="sr-foot">В архиве ${num(d.messages, 0)} ${plural(d.messages, "сообщение", "сообщения", "сообщений")} из ${d.archived_chats} ${plural(d.archived_chats, "чата", "чатов", "чатов")} — всё, что Cardinal видел с момента обновления.
                    ${d.job && d.job.running ? `<br>Загружаю старые переписки: ${d.job.done} из ${d.job.total}…` : `<br><button class="link-btn" id="sr-index">Загрузить старые переписки (последние 50 чатов)</button>`}</div>`;
            $("sr-back").addEventListener("click", () => { chatState.deep = null; drawList(); });
            const ix = $("sr-index");
            if (ix) ix.addEventListener("click", async () => {
                ix.disabled = true;
                try {
                    await api("/api/chats/index", { method: "POST", body: { count: 50 } });
                    toast("Загружаю старые переписки — это займёт около минуты");
                    const t = setInterval(async () => {
                        if (!alive() || !chatState.deep) return clearInterval(t);
                        try {
                            const a = await api("/api/chats/archive");
                            chatState.deep = { ...chatState.deep, ...a };
                            if (!a.job || !a.job.running) { clearInterval(t); runDeep(chatState.deep.q); } else drawDeep();
                        } catch (e) { clearInterval(t); }
                    }, 2500);
                    chatTimers.push(t);
                } catch (err) { toast(err.message, "err"); ix.disabled = false; }
            });
        }
        $("cd-items").addEventListener("click", (e) => {
            const dc = e.target.closest("[data-deep-chat]");
            if (dc) {
                const id = +dc.dataset.deepChat;
                if (id) openDeskChat(chatState.list.find((x) => x.id === id) || { id, name: dc.dataset.deepName });
                else openChatByName(dc.dataset.deepName);
                return;
            }
            const el = e.target.closest("[data-chat]");
            if (!el) return;
            const c = chatState.list.find((x) => x.id === +el.dataset.chat);
            if (c && c.id !== chatState.sel) openDeskChat(c);
        });
        chatTimers.push(setInterval(async () => {
            if (!alive() || document.hidden) return;
            try { await loadChats(); if (alive()) drawList(); } catch (e) {}
        }, 5000));

        function openDeskChat(c) {
            chatState.sel = c.id;
            drawList();
            const token = ++convSeq;
            const convAlive = () => alive() && token === convSeq;
            $("cd-conv").innerHTML = `
                <div class="cd-head">${chatAva(c)}
                    <div class="body"><div class="t">${esc(c.name)}</div><div class="s" id="cd-sub">Переписка на FunPay</div></div>
                    <button class="btn-sm" id="cd-open">${icon("external")}<span>Открыть на FunPay</span></button></div>
                <div class="chat-scroll">${sk(44, 8, 16)}${sk(44, 8, 16)}${sk(44, 8, 16)}</div>
                ${composerHtml()}`;
            $("cd-open").addEventListener("click", () => openLink(`https://funpay.com/chat/?node=${c.id}`));
            mountConversation($("cd-conv"), c, convAlive);
            loadBuyerCard(c, convAlive);
        }
        const again = chatState.sel && chatState.list.find((x) => x.id === chatState.sel);
        if (again) openDeskChat(again);
    }

    async function loadBuyerCard(c, alive) {
        const side = $("cd-side");
        if (!side) return;
        side.innerHTML = sk(170) + sk(240);
        let b;
        try { b = await api(`/api/chats/${c.id}/buyer`); } catch (e) { if (alive()) side.innerHTML = errorBox(e); return; }
        if (!alive()) return;
        const sums = Object.entries(b.sum || {}).map(([cur, v]) => money(v, cur)).join(" · ") || "—";
        const draw = () => {
            side.innerHTML = `
                <div class="panel buyer-card">
                    <div class="bc-top">${chatAva(c)}<div class="body"><div class="t">${esc(b.name || c.name)}</div>
                        <div class="s">${b.blacklisted ? `<span class="badge refunded plain">В чёрном списке</span>` : "Покупатель"}</div></div></div>
                    <div class="bc-stats">
                        <div><div class="v tnum">${b.orders === null ? "—" : b.count}</div><div class="l">${plural(b.count, "заказ", "заказа", "заказов")}</div></div>
                        <div><div class="v tnum">${b.orders === null ? "—" : esc(sums)}</div><div class="l">потратил</div></div>
                    </div>
                    ${b.profile ? `<button class="btn secondary" data-link="${esc(b.profile)}">${icon("external")}<span>Профиль на FunPay</span></button>` : ""}
                    <button class="btn ${b.blacklisted ? "secondary" : "danger"}" id="bc-bl">${icon(b.blacklisted ? "check" : "userx")}<span>${b.blacklisted ? "Убрать из чёрного списка" : "В чёрный список"}</span></button>
                </div>
                ${sectionHead("Заказы покупателя")}
                ${b.orders === null ? `<div class="empty-sm">Не удалось загрузить заказы с FunPay</div>`
                    : b.orders.length ? `<div class="list bc-orders">${b.orders.map((o) => `
                        <div class="item clickable" data-link="https://funpay.com/orders/${esc(o.id)}/" role="button">
                            <div class="body"><div class="t"><span class="txt">#${esc(o.id)}</span></div><div class="s">${esc(o.description || "")}</div></div>
                            <div class="right"><div class="price tnum">${money(o.price, o.currency)}</div>${statusBadge(o.status)}</div>
                        </div>`).join("")}</div>`
                    : `<div class="empty-sm">Этот покупатель ещё ничего не покупал у вас</div>`}`;
            $("bc-bl").addEventListener("click", async () => {
                const name = b.name || c.name;
                if (!b.blacklisted && !(await confirmDialog(`Добавить ${name} в чёрный список? Cardinal перестанет выдавать ему товар и отвечать по правилам чёрного списка.`))) return;
                try {
                    await blacklistChange(b.blacklisted ? "remove" : "add", name);
                    b.blacklisted = !b.blacklisted;
                    const item = chatState.list && chatState.list.find((x) => x.id === c.id);
                    if (item) item.blacklisted = b.blacklisted;
                    draw();
                } catch (e) { toast(e.message, "err"); }
            });
        };
        draw();
    }

    // ---------- Склад автовыдачи ----------
    // Товарные файлы Cardinal (storage/products) и лоты с автовыдачей (configs/auto_delivery.cfg).
    // Телефон: посмотреть остатки и пополнить. Панель: ещё подключение лотов, текст выдачи, пороги, удаление.
    let stockData = null, stockSel = null;
    const STOCK_ST = { empty: ["Пусто", "refunded", "tint-red"], low: ["Заканчивается", "paid", "tint-amber"], ok: ["В наличии", "closed", "tint-green"] };
    const stockBadge = (f) => `<span class="badge ${STOCK_ST[f.status][1]}">${STOCK_ST[f.status][0]}</span>`;
    const pcs = (n) => `${num(n, 0)} шт.`;

    async function loadStock() {
        const d = await api("/api/stock");
        stockData = d;
        state.stock = { empty: d.empty, low: d.low_count };
        updateStockBadge();
        return d;
    }
    function updateStockBadge() {
        const el = $("nav-stock");
        if (!el) return;
        const s = state.stock || {}, n = (s.empty || 0) + (s.low || 0);
        el.textContent = n || "";
        el.className = `cnt ${s.empty ? "red" : "amber"}`;
    }
    function stockSummary(d) {
        if (!d) return "Товары для автовыдачи Cardinal";
        const parts = [`${num(d.total, 0)} ${plural(d.total, "товар", "товара", "товаров")}`];
        if (d.empty) parts.push(`пусто: ${d.empty}`);
        if (d.low_count) parts.push(`заканчивается: ${d.low_count}`);
        return parts.join(" · ");
    }
    // вход в склад со страницы «Лоты»
    function stockEntryHtml() {
        const s = state.stock || {};
        const tint = s.empty ? "tint-red" : s.low ? "tint-amber" : "tint-brand";
        return `<button class="card stock-entry" id="stock-entry">
            <div class="ic ${tint}">${icon("inbox")}</div>
            <div class="body"><div class="t">Склад автовыдачи</div><div class="s" id="stock-entry-s">${esc(stockSummary(stockData))}</div></div>
            <span class="chev">${icon("chevron")}</span></button>`;
    }
    function bindStockEntry() {
        const b = $("stock-entry");
        if (!b) return;
        b.addEventListener("click", () => { haptic(); if (isDesktop()) setTab("stock"); else push({ type: "stock" }); });
        loadStock().then((d) => { const s = $("stock-entry-s"); if (s) s.textContent = stockSummary(d); }).catch(() => {});
    }

    function newFileSheet(after) {
        const sh = openSheet(`<div class="head"><div><div class="title">Новый файл с товарами</div>
                <div class="sub">Например: «Ключи CS2» или «Аккаунты Rust»</div></div></div>
            <div class="list"><div class="field"><label for="nf-name">Название</label>
                <input type="text" id="nf-name" maxlength="60" placeholder="Название файла" autocomplete="off">
                <div class="hint">Буквы, цифры, пробел, «-» и «_»</div></div></div>
            <button class="btn" id="nf-save" style="margin-top:14px">Создать</button>`);
        const inp = sh.querySelector("#nf-name");
        setTimeout(() => inp.focus(), 250);
        const save = async () => {
            const name = inp.value.trim();
            if (!name) return inp.focus();
            try {
                const r = await api("/api/stock/file", { method: "POST", body: { action: "create", name } });
                closeSheet(); notify("success"); toast(`Файл «${r.name}» создан`);
                after(r.name);
            } catch (e) { toast(e.message, "err"); notify("error"); }
        };
        sh.querySelector("#nf-save").addEventListener("click", save);
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
    }

    async function addProducts(name, textarea, dedupe) {
        const text = textarea.value;
        if (!text.trim()) { textarea.focus(); return null; }
        try {
            const r = await api("/api/stock/file", { method: "POST", body: { action: "add", name, text, dedupe } });
            textarea.value = "";
            textarea.dispatchEvent(new Event("input"));
            notify("success");
            toast(r.added ? `Добавлено: ${pcs(r.added)}${r.skipped ? `, повторов пропущено: ${r.skipped}` : ""}` : `Все ${pcs(r.skipped)} уже есть в файле`);
            return r;
        } catch (e) { toast(e.message, "err"); notify("error"); return null; }
    }

    function addBoxHtml() {
        return `<div class="stock-add">
            <textarea class="stock-ta" id="sa-text" placeholder="Каждый товар — с новой строки.&#10;Например: логин:пароль или ключ"></textarea>
            <div class="stock-add-f"><label class="chk"><input type="checkbox" id="sa-dedupe" checked> Пропускать повторы</label>
                <span class="grow muted" id="sa-n"></span>
                <button class="btn-sm primary" id="sa-add">${icon("plus")}<span>Добавить</span></button></div></div>`;
    }
    function bindAddBox(name, after) {
        const ta = $("sa-text"), n = $("sa-n");
        ta.addEventListener("input", () => {
            const c = ta.value.split("\n").filter((x) => x.trim()).length;
            n.textContent = c ? pcs(c) : "";
        });
        $("sa-add").addEventListener("click", async () => {
            const b = $("sa-add");
            b.disabled = true;
            const r = await addProducts(name, ta, $("sa-dedupe").checked);
            b.disabled = false;
            if (r) after(r);
        });
    }

    function itemsHtml(items, canDelete = true) {
        return items.map((x) => `<div class="stock-item"><span class="n">${x.i + 1}</span><span class="x">${esc(x.text)}</span>
            ${canDelete ? `<button class="del" data-del-item="${x.i}" title="Удалить товар">${icon("trash")}</button>` : ""}</div>`).join("");
    }
    async function deleteItem(name, item) {
        if (!(await confirmDialog(`Удалить товар из «${name}»?\n\n${item.text.slice(0, 200)}`))) return false;
        try {
            await api("/api/stock/file", { method: "POST", body: { action: "remove", name, index: item.i, text: item.text } });
            toast("Товар удалён");
            return true;
        } catch (e) { toast(e.message, "err"); notify("error"); return false; }
    }

    async function renderStock(screen, alive) {
        const desk = isDesktop();
        paint(pageHead("Склад", "Загружаю…") + sk(70) + sk(66 * 3));
        let d;
        try { d = await loadStock(); } catch (e) { if (alive()) paint(pageHead("Склад") + errorBox(e)); return; }
        if (!alive()) return;
        return desk ? stockDesk(d, alive) : stockMobile(d, alive);
    }

    const adOffBox = (d) => d.autodelivery ? "" : `<div class="warn-box">${icon("alert")}<p>Автовыдача выключена в настройках Cardinal — товары сейчас не выдаются. Включить: «Настройки» → «Автовыдача».</p></div>`;

    // ----- телефон -----
    function stockMobile(d, alive) {
        const right = `<button class="icon-btn" id="sf-new" aria-label="Новый файл">${icon("plus")}</button>`;
        const list = d.files.length ? `<div class="list">${d.files.map((f) => `
            <div class="item clickable stock-file" data-file="${esc(f.name)}" role="button">
                <div class="ic ${STOCK_ST[f.status][2]}">${icon("inbox")}</div>
                <div class="body"><div class="t"><span class="txt">${esc(f.name)}</span></div>
                    <div class="s">${f.lots.length ? esc(f.lots.join(", ")) : "не подключён к лотам"}</div></div>
                <div class="right"><span class="cnt">${num(f.count, 0)}</span>${f.status !== "ok" ? stockBadge(f) : ""}</div>
            </div>`).join("")}</div>`
            : emptyBox("inbox", "Товаров пока нет", "Создайте файл и добавьте товары — Cardinal будет выдавать их покупателям сразу после оплаты.")
              + `<button class="btn" id="sf-new2" style="max-width:360px;margin:0 auto">${icon("plus")}Создать файл</button>`;
        paint(`${pageHead("Склад", esc(stockSummary(d)), right)}${adOffBox(d)}${list}
            <div class="note">Подключить лот к автовыдаче и изменить текст выдачи можно в Панели на компьютере или в Telegram-боте Cardinal.</div>`);
        const open = (name) => push({ type: "stockfile", name });
        [$("sf-new"), $("sf-new2")].forEach((b) => b && b.addEventListener("click", () => newFileSheet(open)));
        $view.querySelectorAll("[data-file]").forEach((el) => el.addEventListener("click", () => { haptic(); open(el.dataset.file); }));
    }

    async function renderStockFile(screen, alive) {
        const name = screen.name;
        paint(pageHead(name, "Загружаю…") + sk(150) + sk(66 * 4));
        let f;
        try { f = await api(`/api/stock/file?name=${encodeURIComponent(name)}`); }
        catch (e) { if (alive()) paint(pageHead(name) + errorBox(e)); return; }
        if (!alive()) return;
        let showAll = false;
        const draw = () => {
            const items = showAll ? f.items : f.items.slice(0, 100);
            $("sf-items").innerHTML = f.count ? `<div class="stock-items">${itemsHtml(items)}</div>
                ${items.length < f.items.length ? `<button class="btn secondary" id="sf-more" style="margin-top:10px">Показать все (${num(f.count, 0)})</button>` : ""}`
                : `<div class="empty-sm">В файле пока нет товаров</div>`;
            const more = $("sf-more");
            if (more) more.addEventListener("click", () => { showAll = true; draw(); });
            $("sf-sub").innerHTML = `${pcs(f.count)} · ${stockBadge(f)}`;
        };
        paint(`${pageHead(name, `<span id="sf-sub"></span>`)}
            ${f.lots.length ? `<div class="note" style="margin:-8px 4px 12px">Выдаётся в лотах: ${esc(f.lots.join(", "))}</div>` : ""}
            <div class="card">${addBoxHtml()}</div>
            ${sectionHead("Товары")}<div id="sf-items"></div>`);
        draw();
        const reload = async () => { try { f = await api(`/api/stock/file?name=${encodeURIComponent(name)}`); if (alive()) draw(); } catch (e) {} };
        bindAddBox(name, reload);
        $("sf-items").addEventListener("click", async (e) => {
            const b = e.target.closest("[data-del-item]");
            if (!b) return;
            const item = f.items.find((x) => x.i === +b.dataset.delItem);
            if (item && await deleteItem(name, item)) reload();
        });
    }

    // ----- Панель -----
    function stockDesk(d, alive) {
        const lotsCnt = d.lots.length;
        const kpi = (ic, tint, label, v, foot = "") => `<div class="kpi"><div class="h"><div class="ic ${tint}">${icon(ic)}</div>${label}</div><div class="v">${v}</div><div class="f">${foot}</div></div>`;
        const right = `<div style="display:flex;gap:8px"><button class="btn-sm" id="sd-new">${icon("plus")}<span>Новый файл</span></button>
            <button class="btn-sm primary" id="sd-link">${icon("tag")}<span>Подключить лот</span></button></div>`;
        if (!d.files.find((f) => f.name === stockSel)) stockSel = d.files.length ? d.files[0].name : null;
        paint(`${pageHead("Склад автовыдачи", esc(stockSummary(d)), right)}${adOffBox(d)}
            <div class="kpis">
                ${kpi("inbox", "tint-brand", "Товаров на складе", num(d.total, 0), `в ${d.files.length} ${plural(d.files.length, "файле", "файлах", "файлах")}`)}
                ${kpi("alert", d.empty ? "tint-red" : "tint-green", "Пустых файлов", d.empty, d.empty ? "автовыдача по ним не сработает" : "всё в наличии")}
                ${kpi("clock", d.low_count ? "tint-amber" : "tint-green", "Заканчивается", d.low_count, "порог настраивается у файла")}
                ${kpi("tag", "tint-brand", "Лотов с автовыдачей", lotsCnt, d.free_lots.length ? `ещё ${d.free_lots.length} без автовыдачи` : "")}
            </div>
            <div class="stock-grid">
                <div class="panel stock-files"><div class="panel-h"><div class="ic tint-brand">${icon("inbox")}</div><div><div class="t">Товарные файлы</div><div class="s">storage/products</div></div></div>
                    <div id="sd-files"></div></div>
                <div class="panel" id="sd-file"></div>
            </div>
            <div class="panel" style="margin-top:14px"><div class="panel-h"><div class="ic tint-brand">${icon("tag")}</div>
                <div style="flex:1"><div class="t">Лоты с автовыдачей</div><div class="s">Cardinal отправляет покупателю текст выдачи, а вместо $product — товар из файла</div></div></div>
                <div id="sd-lots"></div></div>`);

        const drawFiles = () => {
            $("sd-files").innerHTML = d.files.length ? `<div class="list" style="box-shadow:none">${d.files.map((f) => `
                <div class="item clickable stock-file ${f.name === stockSel ? "sel" : ""}" data-file="${esc(f.name)}" role="button">
                    <div class="ic ${STOCK_ST[f.status][2]}">${icon("inbox")}</div>
                    <div class="body"><div class="t"><span class="txt">${esc(f.name)}</span></div>
                        <div class="s">${f.lots.length ? `${f.lots.length} ${plural(f.lots.length, "лот", "лота", "лотов")}` : "без лотов"}</div></div>
                    <div class="right"><span class="cnt">${num(f.count, 0)}</span>${f.status !== "ok" ? stockBadge(f) : ""}</div></div>`).join("")}</div>`
                : `<div class="empty-sm">Файлов пока нет — создайте первый кнопкой «Новый файл».</div>`;
        };
        drawFiles();
        drawStockLots(d, alive);
        if (stockSel) openStockFile(stockSel, alive); else $("sd-file").innerHTML = emptyBox("inbox", "Нет товарных файлов", "Создайте файл, добавьте в него товары и подключите к лоту — Cardinal будет выдавать их сам.");

        $("sd-files").addEventListener("click", (e) => {
            const el = e.target.closest("[data-file]");
            if (!el || el.dataset.file === stockSel) return;
            stockSel = el.dataset.file;
            drawFiles();
            openStockFile(stockSel, alive);
        });
        $("sd-new").addEventListener("click", () => newFileSheet((name) => { stockSel = name; render(true); }));
        $("sd-link").addEventListener("click", () => linkLotSheet(d));
    }

    async function openStockFile(name, alive) {
        const box = $("sd-file");
        box.innerHTML = sk(40) + sk(160) + sk(200);
        let f;
        try { f = await api(`/api/stock/file?name=${encodeURIComponent(name)}`); }
        catch (e) { if (alive() && stockSel === name) box.innerHTML = errorBox(e); return; }
        if (!alive() || stockSel !== name) return;
        let q = "";
        box.innerHTML = `<div class="panel-h"><div class="ic ${STOCK_ST[f.status][2]}">${icon("inbox")}</div>
                <div style="flex:1;min-width:0"><div class="t">${esc(f.name)}</div><div class="s" id="sd-sub"></div></div>
                <button class="btn-sm" id="sd-clear">${icon("trash")}<span>Очистить</span></button>
                <button class="btn-sm danger-sm" id="sd-del" title="Удалить файл">${icon("trash")}<span>Удалить файл</span></button></div>
            ${addBoxHtml()}
            <div class="stock-tools"><label class="search">${icon("search")}<input id="sd-q" type="search" placeholder="Найти товар" autocomplete="off"></label>
                <label class="low">Заканчивается, если осталось ≤ <input type="number" id="sd-low" min="0" max="100000" value="${f.low}"></label></div>
            <div id="sd-items"></div>`;
        const draw = () => {
            const items = q ? f.items.filter((x) => x.text.toLowerCase().includes(q)) : f.items;
            $("sd-sub").innerHTML = `${pcs(f.count)} · ${stockBadge(f)}${f.lots.length ? ` · ${esc(f.lots.join(", "))}` : " · не подключён к лотам"}`;
            $("sd-items").innerHTML = items.length ? `<div class="stock-items">${itemsHtml(items)}</div>
                ${f.count > f.items.length ? `<div class="note">Показаны первые ${num(f.items.length, 0)} из ${num(f.count, 0)}</div>` : ""}`
                : `<div class="empty-sm">${f.count ? "Ничего не найдено" : "В файле пока нет товаров — вставьте их выше"}</div>`;
        };
        draw();
        const reload = async () => {
            try { f = await api(`/api/stock/file?name=${encodeURIComponent(name)}`); } catch (e) { return; }
            if (!alive() || stockSel !== name) return;
            draw();
            refreshStockLists(alive);
        };
        bindAddBox(name, reload);
        $("sd-q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });
        $("sd-items").addEventListener("click", async (e) => {
            const b = e.target.closest("[data-del-item]");
            if (!b) return;
            const item = f.items.find((x) => x.i === +b.dataset.delItem);
            if (item && await deleteItem(name, item)) reload();
        });
        $("sd-low").addEventListener("change", async (e) => {
            try {
                await api("/api/stock/file", { method: "POST", body: { action: "low", name, value: e.target.value } });
                toast("Сохранено"); reload();
            } catch (err) { toast(err.message, "err"); e.target.value = f.low; }
        });
        $("sd-clear").addEventListener("click", async () => {
            if (!f.count || !(await confirmDialog(`Удалить все товары из «${name}» (${pcs(f.count)})?\n\nЭто нельзя отменить.`))) return;
            try { await api("/api/stock/file", { method: "POST", body: { action: "clear", name } }); toast("Файл очищен"); reload(); }
            catch (err) { toast(err.message, "err"); }
        });
        $("sd-del").addEventListener("click", async () => {
            if (!(await confirmDialog(`Удалить файл «${name}»${f.count ? ` вместе с товарами (${pcs(f.count)})` : ""}?\n\nЭто нельзя отменить.`))) return;
            try { await api("/api/stock/file", { method: "POST", body: { action: "delete", name } }); toast("Файл удалён"); stockSel = null; render(true); }
            catch (err) { toast(err.message, "err"); notify("error"); }
        });
    }

    // после пополнения/удаления обновляем список файлов и лоты, не трогая открытый файл
    async function refreshStockLists(alive) {
        let d;
        try { d = await loadStock(); } catch (e) { return; }
        if (!alive()) return;
        $view.querySelectorAll("#sd-files [data-file]").forEach((el) => {
            const f = d.files.find((x) => x.name === el.dataset.file);
            if (!f) return;
            el.querySelector(".right").innerHTML = `<span class="cnt">${num(f.count, 0)}</span>${f.status !== "ok" ? stockBadge(f) : ""}`;
            el.querySelector(".ic").className = `ic ${STOCK_ST[f.status][2]}`;
        });
        drawStockLots(d, alive);
    }

    function drawStockLots(d, alive) {
        const box = $("sd-lots");
        if (!box) return;
        const fileOpts = (cur) => `<option value="">— без файла, только текст —</option>` +
            d.files.map((f) => `<option value="${esc(f.name)}" ${f.file === cur ? "selected" : ""}>${esc(f.name)} (${num(f.count, 0)})</option>`).join("");
        box.innerHTML = d.lots.length ? d.lots.map((l, i) => `
            <div class="ad-row" data-i="${i}">
                <div class="ad-main">
                    <div class="ad-t">${esc(l.title)}</div>
                    <div class="ad-s">${l.file ? (l.missing ? `<span class="badge refunded">файла ${esc(l.file)} нет</span>`
                        : `осталось <b class="${l.count === 0 ? "red" : ""}">${pcs(l.count)}</b>`) : "без товаров из файла"}${l.disabled ? ` · <span class="badge muted plain">выключена</span>` : ""}</div>
                </div>
                <select class="ad-file" data-act="file">${fileOpts(l.file)}</select>
                <span title="Автовыдача для этого лота">${sw(`data-act="on"`, !l.disabled)}</span>
                <button class="btn-sm" data-act="text">${icon("pencil")}<span>Текст</span></button>
                <button class="icon-btn sm" data-act="unlink" title="Отключить автовыдачу">${icon("trash")}</button>
                <div class="ad-edit" hidden>
                    <textarea class="stock-ta" rows="5">${esc(l.response)}</textarea>
                    <div class="stock-add-f"><span class="grow muted">$product — товар из файла, $username — ник покупателя, $order_id — номер заказа</span>
                        <button class="btn-sm" data-act="cancel">Отмена</button><button class="btn-sm primary" data-act="save">Сохранить</button></div>
                </div>
            </div>`).join("")
            : `<div class="empty-sm">Ни один лот не подключён к автовыдаче. Нажмите «Подключить лот» вверху.</div>`;

        // revert: при ошибке перерисовать строки, чтобы переключатель/список вернулись как было.
        // Для текста выдачи не нужно — пусть редактор останется открытым с введённым текстом.
        const update = async (l, body, ok, revert = true) => {
            try {
                await api("/api/stock/lot", { method: "POST", body: { action: "update", title: l.title, ...body } });
                toast(ok); notify("success");
                refreshStockLists(alive);
                return true;
            } catch (e) { toast(e.message, "err"); notify("error"); if (revert) refreshStockLists(alive); return false; }
        };
        box.onchange = (e) => {
            const row = e.target.closest(".ad-row");
            if (!row) return;
            const l = d.lots[+row.dataset.i];
            if (e.target.dataset.act === "file") update(l, { file: e.target.value }, e.target.value ? `«${l.title}» выдаёт товары из «${e.target.value}»` : "Файл отключён от лота");
            if (e.target.dataset.act === "on") update(l, { disabled: !e.target.checked }, e.target.checked ? "Автовыдача включена" : "Автовыдача лота выключена");
        };
        box.onclick = async (e) => {
            const b = e.target.closest("[data-act]");
            const row = b && b.closest(".ad-row");
            if (!row || b.tagName === "SELECT" || b.tagName === "INPUT") return;
            const l = d.lots[+row.dataset.i], edit = row.querySelector(".ad-edit");
            if (b.dataset.act === "text") { edit.hidden = !edit.hidden; if (!edit.hidden) edit.querySelector("textarea").focus(); }
            if (b.dataset.act === "cancel") { edit.hidden = true; edit.querySelector("textarea").value = l.response; }
            if (b.dataset.act === "save") {
                const response = edit.querySelector("textarea").value;
                if (await update(l, { response }, "Текст выдачи сохранён", false)) l.response = response;
            }
            if (b.dataset.act === "unlink") {
                if (!(await confirmDialog(`Отключить автовыдачу у лота «${l.title}»?\n\nТовары в файле останутся.`))) return;
                try { await api("/api/stock/lot", { method: "POST", body: { action: "unlink", title: l.title } }); toast("Автовыдача отключена"); render(true); }
                catch (err) { toast(err.message, "err"); }
            }
        };
    }

    function linkLotSheet(d) {
        const slug = (t) => t.replace(/[^А-Яа-яЁёA-Za-z0-9_\- ]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 60);
        const sh = openSheet(`<div class="head"><div><div class="title">Подключить лот к автовыдаче</div>
                <div class="sub">После оплаты Cardinal сам отправит покупателю товар из файла</div></div></div>
            <div class="list">
                <div class="field"><label for="ll-q">Лот</label>
                    ${d.free_lots.length ? `<input type="search" id="ll-q" placeholder="Найти среди ваших лотов" autocomplete="off">
                        <div class="ll-lots" id="ll-lots"></div>` : ""}
                    <input type="text" id="ll-title" placeholder="Название лота, как на FunPay" style="margin-top:8px">
                    <div class="hint">${d.free_lots.length ? "Выберите из списка или впишите название вручную" : "Впишите название лота точно как на FunPay"}</div></div>
                <div class="field"><label for="ll-file">Товары берутся из файла</label>
                    <select id="ll-file"><option value="__new">+ Новый файл</option>${d.files.map((f) => `<option value="${esc(f.name)}">${esc(f.name)} (${num(f.count, 0)})</option>`).join("")}<option value="">Без файла — только текст</option></select>
                    <input type="text" id="ll-new" placeholder="Название нового файла" maxlength="60" style="margin-top:8px"></div>
                <div class="field"><label for="ll-resp">Текст выдачи</label>
                    <textarea id="ll-resp">Спасибо за покупку, $username!\n\nВот твой товар:\n$product</textarea>
                    <div class="hint">$product — товар из файла, $username — ник покупателя</div></div>
            </div>
            <button class="btn" id="ll-save" style="margin-top:14px">Подключить</button>`);
        const title = sh.querySelector("#ll-title"), file = sh.querySelector("#ll-file"), nf = sh.querySelector("#ll-new"), lotsBox = sh.querySelector("#ll-lots");
        const syncNew = () => { nf.hidden = file.value !== "__new"; };
        const drawLots = (q = "") => {
            if (!lotsBox) return;
            const list = d.free_lots.filter((l) => !q || l.title.toLowerCase().includes(q)).slice(0, 50);
            lotsBox.innerHTML = list.length ? list.map((l) => `<button class="ll-lot ${l.title === title.value ? "sel" : ""}" data-t="${esc(l.title)}">
                <span>${esc(l.title)}</span><small>${esc(l.sub)}</small></button>`).join("") : `<div class="empty-sm">Не найдено</div>`;
        };
        drawLots();
        syncNew();
        if (lotsBox) {
            sh.querySelector("#ll-q").addEventListener("input", (e) => drawLots(e.target.value.trim().toLowerCase()));
            lotsBox.addEventListener("click", (e) => {
                const b = e.target.closest("[data-t]");
                if (!b) return;
                title.value = b.dataset.t;
                if (file.value === "__new" && !nf.value) nf.value = slug(b.dataset.t);
                drawLots(sh.querySelector("#ll-q").value.trim().toLowerCase());
            });
        }
        file.addEventListener("change", syncNew);
        sh.querySelector("#ll-save").addEventListener("click", async () => {
            const body = { action: "link", title: title.value.trim(), response: sh.querySelector("#ll-resp").value };
            if (!body.title) return title.focus();
            if (file.value === "__new") { if (!nf.value.trim()) return nf.focus(); body.new_file = nf.value.trim(); }
            else if (file.value) body.file = file.value;
            try {
                const r = await api("/api/stock/lot", { method: "POST", body });
                closeSheet(); notify("success");
                toast(`Лот подключён${r.file ? ` — товары из «${r.file.replace(/\.txt$/, "")}»` : ""}`);
                if (r.file) stockSel = r.file.replace(/\.txt$/, "");
                render(true);
            } catch (e) { toast(e.message, "err"); notify("error"); }
        });
    }

    // ---------- Статистика продаж (Панель) ----------
    let statsDays = 30, statsData = null;
    const STATS_PERIODS = [[7, "7 дней"], [30, "30 дней"], [90, "90 дней"], [365, "Год"]];
    const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

    /** Столбики: items = [{label, value, tip}]. Подсказка — при наведении. */
    function barsChart(el, items, opts = {}) {
        const chart = {
            draw() {
                const W = Math.max(280, el.clientWidth || 700), H = opts.height || 220;
                const padL = opts.noAxis ? 8 : 52, padR = 8, padT = 12, padB = 24;
                const vals = items.map((i) => i.value);
                const max = niceMax(Math.max(0, ...vals) * 1.08 || 1);
                const iw = W - padL - padR, ih = H - padT - padB, n = items.length || 1;
                const step = iw / n, bw = Math.max(2, Math.min(34, step * 0.68));
                const fmt = opts.fmt || shortMoney;
                let g = "";
                if (!opts.noAxis) for (let k = 0; k <= 4; k++) {
                    const y = padT + ih * (1 - k / 4);
                    g += `<line class="grid-l" x1="${padL}" x2="${W - padR}" y1="${y}" y2="${y}"/>
                        <text class="axis-t" x="${padL - 8}" y="${y + 4}" text-anchor="end">${k ? fmt(max * k / 4) : "0"}</text>`;
                }
                const every = Math.max(1, Math.ceil(n / (opts.maxLabels || 12)));
                const bars = items.map((it, i) => {
                    const h = it.value > 0 ? Math.max(2, ih * it.value / max) : 0;
                    const x = padL + i * step + (step - bw) / 2, y = padT + ih - h;
                    return `<g class="bar-g"><rect class="bar-hit" x="${padL + i * step}" y="${padT}" width="${step}" height="${ih}"><title>${esc(it.tip)}</title></rect>
                        <rect class="bar-r ${it.hl ? "hl" : ""}" x="${x}" y="${y}" width="${bw}" height="${h}" rx="${Math.min(4, bw / 2)}"><title>${esc(it.tip)}</title></rect></g>`;
                }).join("");
                const labels = items.map((it, i) => i % every === 0 || i === n - 1 && n <= 31
                    ? `<text class="axis-t" x="${padL + i * step + step / 2}" y="${H - 6}" text-anchor="middle">${esc(it.label)}</text>` : "").join("");
                el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}">${g}<line class="grid-l" x1="${padL}" x2="${W - padR}" y1="${padT + ih}" y2="${padT + ih}"/>${bars}${labels}</svg>`;
            },
        };
        charts.push(chart);
        chart.draw();
        return chart;
    }

    function statsMoney(sum, main) {
        const entries = Object.entries(sum || {}).sort((a, b) => (b[0] === main) - (a[0] === main) || b[1] - a[1]);
        if (!entries.length) return money(0, main || "₽");
        return entries.map(([cur, v], i) => i ? `<small>+ ${money(v, cur)}</small>` : money(v, cur)).join(" ");
    }

    function statsCsv(d) {
        const rows = [["Дата", "Номер", "Товар", "Покупатель", "Кол-во", "Цена", "Валюта", "Статус", "Раздел"]];
        const st = { paid: "Оплачен", closed: "Закрыт", refunded: "Возврат", partially_refunded: "Частичный возврат" };
        for (const o of d.orders) rows.push([o.date ? o.date.replace("T", " ").slice(0, 16) : "", o.id, o.description, o.buyer,
            o.amount || 1, String(o.price).replace(".", ","), o.currency, st[o.status] || o.status, o.subcategory || ""]);
        const csv = "﻿" + rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";")).join("\r\n");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        a.download = `funpay-orders-${new Date().toISOString().slice(0, 10)}-${d.summary.days}d.csv`;
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        toast(`Скачан файл: ${num(d.orders.length, 0)} заказов — открывается в Excel`);
    }

    async function renderStats(screen, alive, refresh) {
        const right = () => `<div class="st-head">
            <div class="chips st-periods">${STATS_PERIODS.map(([v, l]) => `<button class="chip ${v === statsDays ? "active" : ""}" data-days="${v}">${l}</button>`).join("")}</div>
            <button class="btn-sm" id="st-csv" title="Скачать заказы за период (CSV для Excel)" ${statsData ? "" : "disabled"}>${icon("upload")}<span>CSV</span></button>
            <button class="icon-btn" id="st-reload" title="Загрузить заново с FunPay">${icon("refresh")}</button></div>`;
        const bindHead = () => {
            $view.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
                const v = +b.dataset.days;
                if (v === statsDays) return;
                haptic("light"); statsDays = v; statsData = null; render();
            }));
            $("st-reload").addEventListener("click", () => { statsData = null; render(true); });
            const c = $("st-csv"); if (c) c.addEventListener("click", () => statsData && statsCsv(statsData));
        };
        paint(pageHead("Статистика продаж", `<span id="st-progress">Загружаю заказы с FunPay…</span>`, right()) +
            `<div class="kpis k5">${sk(108, 0).repeat(5)}</div>` + sk(280) + sk(240));
        bindHead();

        let d, first = true;
        while (true) {
            try { d = await api(`/api/stats?days=${statsDays}${refresh === true && first ? "&refresh=1" : ""}`); }
            catch (e) { if (alive()) { paint(pageHead("Статистика продаж", "", right()) + errorBox(e)); bindHead(); } return; }
            first = false;
            if (!alive()) return;
            if (d.ready) break;
            const p = $("st-progress");
            if (p) p.textContent = d.pages ? `Загружаю заказы с FunPay… страниц: ${d.pages}` : "Загружаю заказы с FunPay…";
            await new Promise((r) => setTimeout(r, 1500));
            if (!alive()) return;
        }
        statsData = d;
        const s = d.summary, main = s.currency || "₽";
        const period = STATS_PERIODS.find(([v]) => v === s.days)[1].toLowerCase();
        const sub = `За ${s.days === 365 ? "год" : period} · ${num(d.orders.length, 0)} ${plural(d.orders.length, "заказ", "заказа", "заказов")} · обновлено ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
        const kpi = (ic, tint, label, v, foot) => `<div class="kpi"><div class="h"><div class="ic ${tint}">${icon(ic)}</div>${label}</div><div class="v">${v}</div><div class="f">${foot}</div></div>`;

        // по дням; за год — по месяцам
        let series;
        if (s.days === 365) {
            const m = new Map();
            for (const x of s.by_day) {
                const k = x.date.slice(0, 7);
                const e = m.get(k) || { count: 0, v: 0 };
                e.count += x.count; e.v += (x.sum[main] || 0);
                m.set(k, e);
            }
            series = [...m.entries()].map(([k, e]) => ({ label: MONTHS_SHORT[+k.slice(5, 7) - 1], value: e.v,
                tip: `${MONTHS_SHORT[+k.slice(5, 7) - 1]} ${k.slice(0, 4)}: ${money(e.v, main)} · ${e.count} ${plural(e.count, "заказ", "заказа", "заказов")}` }));
        } else {
            series = s.by_day.map((x) => {
                const dt = dayDate(x.date);
                const v = x.sum[main] || 0;
                return { label: dt.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", ""), value: v, hl: dt.getDay() === 0 || dt.getDay() === 6,
                    tip: `${dt.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" })}: ${money(v, main)} · ${x.count} ${plural(x.count, "заказ", "заказа", "заказов")}` };
            });
        }
        const best = series.reduce((a, b) => (b.value > (a ? a.value : -1) ? b : a), null);
        const hours = s.by_hour.map((c, h) => ({ label: h % 3 === 0 ? String(h) : "", value: c, tip: `${h}:00–${h}:59 — ${c} ${plural(c, "заказ", "заказа", "заказов")}` }));
        const peak = s.by_hour.indexOf(Math.max(...s.by_hour));

        const lotsRows = s.top_lots.map((l) => `<tr><td><div class="desc" title="${esc(l.title)}">${esc(l.title)}</div></td>
            <td class="num">${num(l.count, 0)}</td><td class="num ${l.refunds ? "red-t" : "muted"}">${l.refunds || "—"}</td><td class="num">${statsMoney(l.sum, main)}</td>
            <td class="num muted">${l.unit_cost != null ? money(l.unit_cost, main) : "—"}</td><td class="num">${l.profit != null ? money(l.profit, main) : `<span class="muted">—</span>`}</td></tr>`).join("");
        const pr = d.profit;
        const profitBlock = pr ? `<div class="panel profit-strip"><div class="ic tint-green">${icon("coins")}</div>
                <div><div class="pv tnum">${money(pr.profit, main)}</div><div class="pk">чистая прибыль${pr.margin != null ? ` · маржа ${num(pr.margin, 1)}%` : ""}</div></div>
                <div><div class="pv tnum" style="font-size:17px">${money(pr.cost, main)}</div><div class="pk">себестоимость</div></div>
                ${pr.unknown ? `<div><div class="pv tnum" style="font-size:17px">${pr.unknown}</div><div class="pk">${plural(pr.unknown, "заказ", "заказа", "заказов")} без себестоимости — не в прибыли</div></div>` : ""}
                <div class="grow"></div><button class="btn-sm" id="st-costs">${icon("pencil")}<span>Себестоимость</span></button></div>`
            : `<div class="profit-cta">${icon("coins")}<div class="grow">Укажите, сколько вам стоит товар, — увидите чистую прибыль по дням и товарам.</div><button class="btn-sm primary" id="st-costs">Указать себестоимость</button></div>`;
        const buyersRows = s.top_buyers.map((b) => `<tr data-buyer="${esc(b.id || "")}"><td><div class="who">${chatAva({ name: b.name })}<span class="desc">${esc(b.name)}</span></div></td>
            <td class="num">${num(b.count, 0)}</td><td class="num">${statsMoney(b.sum, main)}</td>
            <td class="num muted">${b.last ? new Date(b.last).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : ""}</td></tr>`).join("");

        paint(`${pageHead("Статистика продаж", esc(sub), right())}
            ${d.partial ? `<div class="warn-box">${icon("alert")}<p>FunPay отдал не всю историю — показаны заказы с ${new Date(d.covered_from).toLocaleDateString("ru-RU")}. Это ограничение, чтобы не нагружать аккаунт запросами.</p></div>` : ""}
            <div class="kpis k5">
                ${kpi("coins", "tint-brand", "Выручка", statsMoney(s.revenue, main), `без возвратов · ${num(s.items, 0)} ${plural(s.items, "товар", "товара", "товаров")}`)}
                ${kpi("box", "tint-blue", "Заказов", num(s.orders, 0), s.paid ? `${s.paid} ждут подтверждения` : "все подтверждены")}
                ${kpi("tag", "tint-violet", "Средний чек", money(s.avg, main), best && best.value ? `лучший день: ${esc(best.label)}` : "")}
                ${kpi("restore", s.refunds ? "tint-red" : "tint-green", "Возвраты", num(s.refunds, 0), `${s.refund_rate}% заказов`)}
                ${kpi("users", "tint-amber", "Покупателей", num(s.buyers, 0), `вернулись снова: ${s.repeat_buyers} (${s.repeat_rate}%)`)}
            </div>
            ${profitBlock}
            <div class="panel" style="margin-bottom:14px"><div class="panel-h"><div class="ic tint-brand">${icon("chart")}</div>
                <div><div class="t">${s.days === 365 ? "Выручка по месяцам" : "Выручка по дням"}</div><div class="s">${main}${s.days !== 365 ? " · выходные выделены" : ""} · наведите на столбик, чтобы увидеть сумму</div></div></div>
                <div class="chart st-chart" id="st-days"></div></div>
            <div class="st-grid">
                <div class="panel"><div class="panel-h"><div class="ic tint-violet">${icon("clock")}</div>
                    <div><div class="t">Когда покупают</div><div class="s">${s.orders ? `чаще всего с ${peak}:00 до ${peak + 1}:00` : "заказов пока нет"}</div></div></div>
                    <div class="chart" id="st-hours"></div></div>
                <div class="panel"><div class="panel-h"><div class="ic tint-amber">${icon("star")}</div><div><div class="t">Постоянные покупатели</div>
                    <div class="s">Топ по выручке · нажмите, чтобы открыть профиль</div></div></div>
                    ${buyersRows ? `<div class="table-wrap"><table class="table st-table"><thead><tr><th>Покупатель</th><th class="num">Заказов</th><th class="num">Сумма</th><th class="num">Последний</th></tr></thead><tbody>${buyersRows}</tbody></table></div>` : `<div class="empty-sm">Пока нет покупателей за этот период</div>`}</div>
            </div>
            <div class="panel" style="margin-top:14px"><div class="panel-h"><div class="ic tint-blue">${icon("tag")}</div><div><div class="t">Что продаётся лучше всего</div><div class="s">Топ-15 товаров по выручке за период</div></div></div>
                ${lotsRows ? `<div class="table-wrap"><table class="table st-table"><thead><tr><th>Товар</th><th class="num">Продаж</th><th class="num">Возвратов</th><th class="num">Выручка</th><th class="num" title="Себестоимость 1 шт.">Себест.</th><th class="num">Прибыль</th></tr></thead><tbody>${lotsRows}</tbody></table></div>` : `<div class="empty-sm">Нет продаж за этот период</div>`}</div>`);
        bindHead();
        barsChart($("st-days"), series, { height: 240, maxLabels: s.days === 7 ? 7 : 12 });
        $("st-costs").addEventListener("click", () => costsSheet(d, () => { statsData = null; render(); }));
        barsChart($("st-hours"), hours, { height: 180, fmt: (v) => num(v, 0), maxLabels: 24 });
        $view.querySelectorAll("tr[data-buyer]").forEach((tr) => tr.addEventListener("click", () => {
            if (tr.dataset.buyer) openLink(`https://funpay.com/users/${tr.dataset.buyer}/`);
        }));
    }

    // ---------- Настройки ----------
    const SETTING_ICONS = {
        autoRaise: ["up", "brand"], autoResponse: ["chat", "blue"], autoDelivery: ["send", "green"],
        multiDelivery: ["layers", "violet"], autoRestore: ["restore", "teal"], autoDisable: ["pause", "amber"],
        sendGreetings: ["smile", "amber"], confirmReminder: ["clock", "blue"], dailyReport: ["chart", "violet"], onlyNewChats: ["sparkle", "violet"], sendReply: ["check", "green"],
        keepSentMessagesUnread: ["eyeoff", "gray"], oldMsgGetMode: ["history", "gray"],
        blockDelivery: ["ban", "red"], blockResponse: ["ban", "red"],
        blockNewMessageNotification: ["belloff", "red"], blockNewOrderNotification: ["belloff", "red"],
        blockCommandNotification: ["belloff", "red"],
        waitReply: ["clock", "amber"], badReviewAlert: ["star", "red"], watchdog: ["shield", "green"], quietHours: ["belloff", "violet"],
    };
    const fieldVal = (i, o) => ((i.fields || []).find((f) => f.option === o) || {}).value;
    const SETTING_PREVIEW = {
        waitReply: (i) => `Напомнить, если не ответили за ${fieldVal(i, "waitReplyMinutes")} мин`,
        watchdog: (i) => `Сообщить, если нет связи дольше ${fieldVal(i, "watchdogMinutes")} мин`,
        quietHours: (i) => `С ${fieldVal(i, "quietFrom")} до ${fieldVal(i, "quietTo")} · ${fieldVal(i, "quietMode") === "hold" ? "копить до утра" : "без звука"}`,
    };

    function viewGroup() {
        const mode = getMode();
        const seg = [["auto", "Авто", "auto"], ["mobile", "Мобильный", "phone"], ["desktop", "Панель", "monitor"]];
        const rows = [];
        if (inTelegram) rows.push(`
            <button class="item clickable" id="set-browser">
                <div class="ic tint-blue">${icon("monitor")}</div>
                <div class="body"><div class="t">Открыть в браузере</div><div class="s">Вход по одноразовой ссылке, без пароля</div></div>
                <div class="chev">${icon("external")}</div>
            </button>`);
        if (desktopPlatform && canFullscreen) rows.push(`
            <button class="item clickable" id="set-full">
                <div class="ic tint-violet">${icon("maximize")}</div>
                <div class="body"><div class="t">Развернуть окно</div><div class="s">В широком окне включится Панель</div></div>
                <div class="chev">${icon("chevron")}</div>
            </button>`);
        if (!inTelegram) rows.push(`
            <button class="item clickable" id="set-logout">
                <div class="ic tint-red">${icon("logout")}</div>
                <div class="body"><div class="t">Выйти</div><div class="s">Завершить сессию в этом браузере</div></div>
            </button>`);
        return `<div class="grp">
            ${sectionHead("Вид приложения")}
            <div class="list">
                <div class="field">
                    <div class="segmented" id="seg-mode">${seg.map(([v, l, ic]) => `<button data-mode="${v}" class="${v === mode ? "active" : ""}" style="display:flex;align-items:center;justify-content:center;gap:6px">${icon(ic)}${l}</button>`).join("")}</div>
                    <div class="hint">«Авто» — Панель в широком окне, мобильный вид — в узком.</div>
                </div>
                ${rows.join("")}
            </div></div>`;
    }

    async function renderSettings(_, alive) {
        const desk = isDesktop();
        paint(pageHead("Настройки") + sk(26, 10, 8) + sk(58 * 6) + sk(26, 10, 8) + sk(58 * 5));
        let d, bl;
        try { [d, bl] = await Promise.all([api("/api/settings"), api("/api/blacklist")]); }
        catch (e) { if (alive()) paint(pageHead("Настройки") + errorBox(e)); return; }
        if (!alive()) return;

        const blRow = `
            <button class="item clickable" id="open-bl">
                <div class="ic tint-red">${icon("users")}</div>
                <div class="body"><div class="t">Список пользователей</div><div class="s">${bl.users.length ? `${bl.users.length} ${plural(bl.users.length, "покупатель", "покупателя", "покупателей")} · переключатели ниже действуют на них` : "Пока пусто — добавьте ник, чтобы ограничения заработали"}</div></div>
                <div class="chev">${icon("chevron")}</div>
            </button>`;
        const byKey = {};
        const preview = (i) => {
            if (SETTING_PREVIEW[i.option]) return SETTING_PREVIEW[i.option](i);
            const t = (i.fields || []).find((f) => f.type === "textarea");
            if (!t) return i.hint;
            const v = String(t.value || "").replace(/\s+/g, " ").trim();
            return v ? `«${v.length > 70 ? v.slice(0, 70) + "…" : v}»` : "Текст не задан — нажмите, чтобы настроить";
        };
        const groups = d.groups.map((g) => `<div class="grp">
            ${sectionHead(g.title)}
            <div class="list">${g.items[0] && g.items[0].section === "BlockList" ? blRow : ""}${g.items.map((i) => {
                const key = `${i.section}.${i.option}`;
                byKey[key] = i;
                const [ic, tint] = SETTING_ICONS[i.option] || (i.section === "ReviewReply" ? ["star", "amber"] : ["sparkle", "gray"]);
                const editable = (i.fields || []).length > 0;
                const sub = editable ? preview(i) : i.hint;
                return `<div class="item ${editable ? "clickable" : ""}" ${editable ? `data-edit="${esc(key)}" role="button"` : ""}>
                    <div class="ic tint-${tint}">${icon(ic)}</div>
                    <div class="body"><div class="t">${esc(i.label)}${editable ? `<span class="edit-hint">${icon("pencil")}</span>` : ""}</div>${sub ? `<div class="s" data-prev="${esc(key)}">${esc(sub)}</div>` : ""}</div>
                    <span data-stop>${sw(`data-s="${esc(i.section)}" data-o="${esc(i.option)}"`, i.value)}</span>
                </div>`;
            }).join("")}</div></div>`).join("");
        const note = `<div class="note">Пункты с карандашом открываются по нажатию — там тексты сообщений. Автоответы на команды, автовыдачу и прокси пока можно настроить через бота — команда <code>/menu</code>.</div>`;

        const tgGroup = `<div class="grp">${sectionHead("Telegram")}<div class="list">
            <button class="item clickable" id="open-notif"><div class="ic tint-blue">${icon("tg")}</div><div class="body"><div class="t">Уведомления в Telegram</div><div class="s">Что присылать: заказы, сообщения, отзывы…</div></div><div class="chev">${icon("chevron")}</div></button></div></div>`;
        const plusGroup = `<div class="grp">${sectionHead("Cardinal Plus")}<div class="list">
            <button class="item clickable" id="open-update"><div class="ic tint-brand">${icon("refresh")}</div><div class="body"><div class="t">Обновление</div><div class="s" id="upd-sub">Проверить, есть ли новая версия</div></div><div class="chev">${icon("chevron")}</div></button></div></div>`;
        const dataGroup = desk ? `<div class="grp">${sectionHead("Данные")}<div class="list">
            <button class="item clickable" id="open-backup"><div class="ic tint-green">${icon("shield")}</div><div class="body"><div class="t">Резервная копия</div><div class="s">Сохранить всё одним файлом или восстановить</div></div><div class="chev">${icon("chevron")}</div></button>
            <button class="item clickable" id="open-audit"><div class="ic tint-gray">${icon("history")}</div><div class="body"><div class="t">Журнал действий</div><div class="s">Что и когда менялось в приложении</div></div><div class="chev">${icon("chevron")}</div></button></div></div>` : "";
        paint(pageHead("Настройки", "Изменения применяются сразу") +
            (desk ? `<div class="settings-cols">${viewGroup()}${tgGroup}${groups}${dataGroup}${plusGroup}</div>${note}` : viewGroup() + tgGroup + groups + plusGroup + note));
        $("open-notif").addEventListener("click", openNotifications);
        $("open-update").addEventListener("click", updateSheet);
        api("/api/plus/update").then((u) => {
            const s = $("upd-sub");
            if (!s) return;
            s.innerHTML = u.available ? `<span class="upd-new">Доступна версия ${esc(u.latest.version)}</span> · у вас ${esc(u.version)}` : `Версия ${esc(u.version)}${u.configured ? " · проверить новую" : ""}`;
        }).catch(() => {});
        if (desk) {
            $("open-backup").addEventListener("click", backupSheet);
            $("open-audit").addEventListener("click", () => { haptic(); push({ type: "audit" }); });
        }

        $view.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
            haptic();
            setMode(b.dataset.mode);
            if (b.dataset.mode === "desktop" && !isDesktop()) toast("Окно слишком узкое — откройте в браузере или разверните", "err");
        }));
        $("open-bl").addEventListener("click", () => { haptic(); push({ type: "blacklist" }); });
        const sb = $("set-browser"); if (sb) sb.addEventListener("click", openInBrowser);
        const sf = $("set-full"); if (sf) sf.addEventListener("click", goFullscreen);
        const sl = $("set-logout"); if (sl) sl.addEventListener("click", logout);

        $view.querySelectorAll("input[data-s]").forEach((inp) => inp.addEventListener("change", async () => {
            await saveToggle(inp);
            const item = byKey[`${inp.dataset.s}.${inp.dataset.o}`];
            if (item) item.value = inp.checked;
        }));
        $view.querySelectorAll("[data-edit]").forEach((el) => el.addEventListener("click", (e) => {
            if (e.target.closest("[data-stop]")) return;
            const item = byKey[el.dataset.edit];
            openTextEditor(item, () => {
                const p = $view.querySelector(`[data-prev="${CSS.escape(el.dataset.edit)}"]`);
                if (p) p.textContent = preview(item);
                const sw2 = $view.querySelector(`input[data-s="${CSS.escape(item.section)}"][data-o="${CSS.escape(item.option)}"]`);
                if (sw2) sw2.checked = item.value;
            });
        }));
    }

    async function saveToggle(inp) {
        haptic("medium");
        inp.disabled = true;
        try {
            const r = await api("/api/settings", { method: "POST", body: { section: inp.dataset.s, option: inp.dataset.o, value: inp.checked } });
            inp.checked = r.value;
        } catch (e) { inp.checked = !inp.checked; toast(e.message, "err"); notify("error"); }
        finally { inp.disabled = false; }
    }

    /** Окно редактирования текстов (приветствие, ответ на подтверждение, ответы на отзывы). */
    function openTextEditor(item, onChange) {
        haptic();
        const [ic, tint] = SETTING_ICONS[item.option] || ["star", "amber"];
        const fieldsHtml = item.fields.map((f, idx) => {
            const vars = (f.vars || []).length ? `<div class="vars">${f.vars.map(([v, desc]) =>
                `<button class="var" type="button" data-ins="${esc(v)}" data-target="ed-${idx}" title="${esc(desc)}"><code>${esc(v)}</code><span>${esc(desc)}</span></button>`).join("")}</div>` : "";
            if (f.type === "button") {
                return `<div class="field"><button class="btn secondary" type="button" data-action="${esc(f.action)}">${icon("send")}${esc(f.label)}</button></div>`;
            }
            const input = f.type === "number"
                ? `<input type="number" inputmode="decimal" id="ed-${idx}" value="${esc(f.value)}" min="${f.min ?? 0}" step="any">`
                : f.type === "time"
                ? `<input type="time" id="ed-${idx}" value="${esc(f.value)}" class="time-in">`
                : f.type === "select"
                ? `<select id="ed-${idx}">${(f.options || []).map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(f.value) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
                : `<textarea id="ed-${idx}" rows="6" placeholder="Например: Привет, $username! Спасибо, что написали.">${esc(f.value)}</textarea>`;
            return `<div class="field"><label for="ed-${idx}">${esc(f.label)}</label>${input}${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ""}${vars ? `<div class="hint" style="margin-top:10px">Нажмите, чтобы вставить:</div>${vars}` : ""}</div>`;
        }).join("");

        const sh = openSheet(`
            <div class="detail">
                <div class="head">
                    <div class="ic tint-${tint}" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon(ic)}</div>
                    <div style="flex:1;min-width:0"><div class="title">${esc(item.label)}</div><div class="sub">${esc(item.hint || "Изменения применяются сразу после сохранения")}</div></div>
                </div>
                <div class="list" style="margin-bottom:10px">
                    <div class="item no-icon"><div class="body"><div class="t">Включено</div></div>${sw('id="ed-toggle"', item.value)}</div>
                </div>
                <div class="list">${fieldsHtml}</div>
                <div style="margin-top:14px"><button class="btn" id="ed-save">${icon("check")}Сохранить</button></div>
            </div>`);

        const tgl = sh.querySelector("#ed-toggle");
        tgl.dataset.s = item.section;
        tgl.dataset.o = item.option;
        tgl.addEventListener("change", async () => { await saveToggle(tgl); item.value = tgl.checked; onChange(); });

        sh.querySelectorAll("[data-action]").forEach((b) => b.addEventListener("click", async () => {
            b.disabled = true;
            try {
                const r = await api("/api/automation/action", { method: "POST", body: { action: b.dataset.action } });
                notify("success");
                toast(r.sent ? "Отчёт отправлен в Telegram" : "Отчёт собран, но в боте нет авторизованных пользователей");
            } catch (e) { toast(e.message, "err"); notify("error"); }
            finally { b.disabled = false; }
        }));

        sh.querySelectorAll("[data-ins]").forEach((b) => b.addEventListener("click", () => {
            const ta = sh.querySelector(`#${b.dataset.target}`);
            const v = b.dataset.ins;
            const start = ta.selectionStart ?? ta.value.length, end = ta.selectionEnd ?? ta.value.length;
            ta.setRangeText(v, start, end, "end");
            ta.focus();
            haptic("light");
        }));

        sh.querySelector("#ed-save").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            try {
                for (const [idx, f] of item.fields.entries()) {
                    if (f.type === "button") continue;
                    const val = sh.querySelector(`#ed-${idx}`).value;
                    if (String(val) === String(f.value)) continue;
                    const r = await api("/api/settings/text", { method: "POST", body: { section: item.section, option: f.option, value: val } });
                    f.value = r.value;
                }
                notify("success");
                toast("Сохранено");
                onChange();
                closeSheet();
            } catch (err) { toast(err.message, "err"); notify("error"); }
            finally { btn.disabled = false; }
        });
    }

    // ================= Cardinal+: отзывы, покупатели, план, расписание, копия лота, журнал, резервная копия =================
    const starsHtml = (n, cls = "") => `<span class="stars ${cls}" title="${n} из 5">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= n ? "on" : ""}">★</i>`).join("")}</span>`;
    const tsDay = (ts) => ts ? shortTime(new Date(ts * 1000).toISOString()) : "";
    const tsFull = (ts) => ts ? new Date(ts * 1000).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) : "";
    const waitLabel = (sec) => sec < 60 ? "меньше минуты" : sec < 3600 ? `${Math.floor(sec / 60)} мин` : `${Math.floor(sec / 3600)} ч ${Math.floor(sec % 3600 / 60)} мин`;
    const backLink = () => isDesktop() && stack.length ? `<button class="link-btn back-link" data-back>${icon("chevron", "flip")}Назад</button>` : "";
    document.addEventListener("click", (e) => { if (e.target.closest("[data-back]")) { haptic(); back(); } });
    const bytesToB64 = (buf) => {
        const bytes = new Uint8Array(buf);
        let s = "";
        for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        return btoa(s);
    };
    function downloadB64(name, b64, type = "application/octet-stream") {
        const bin = atob(b64), arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([arr], { type }));
        a.download = name;
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    }
    /** Данные, которые сервер собирает в фоне (заказы за период): ждём, пока будут готовы. */
    async function loadReady(path, alive, onProgress) {
        for (;;) {
            const d = await api(path);
            if (!alive()) return null;
            if (d.ready) return d;
            if (onProgress) onProgress(d.pages || 0);
            await new Promise((r) => setTimeout(r, 1500));
            if (!alive()) return null;
        }
    }
    async function openChatByName(name, chatId) {
        const id = Number(chatId);
        if (Number.isSafeInteger(id) && id > 0) return openChatFromPlugin(id, name);
        try { if (!chatState.list) await loadChats(); } catch (e) {}
        const c = (chatState.list || []).find((x) => x.name === name);
        if (c) openChatFromPlugin(c.id, c.name);
        else toast("Чат с этим покупателем не найден среди последних", "err");
    }

    // ---------- план продаж на месяц (Главная) ----------
    const MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];
    function planBoxHtml(target) {
        if (!target) return `<button class="plan-empty" id="plan-set">${icon("trend")}<span><b>Поставить план продаж на месяц</b><br>Увидите, сколько осталось и успеваете ли</span>${icon("chevron")}</button>`;
        return `<div class="plan-card" id="plan-card"><div class="pc-h"><div class="ic tint-brand">${icon("trend")}</div><div class="grow"><div class="t">План на ${MONTHS_NOM[new Date().getMonth()]}</div><div class="s" id="plan-sub">Считаю продажи за месяц…</div></div>
            <button class="btn-sm" id="plan-set" title="Изменить план">${icon("pencil")}${isDesktop() ? "<span>Изменить</span>" : ""}</button></div><div id="plan-body">${sk(46, 0)}</div></div>`;
    }
    async function fillPlan(alive) {
        const box = $("plan-body");
        if (!box) return;
        let d;
        try { d = await loadReady("/api/plan", alive); } catch (e) { if (alive() && $("plan-body")) $("plan-body").innerHTML = `<div class="note">${esc(e.message)}</div>`; return; }
        if (!d || !$("plan-body")) return;
        const pct = Math.min(100, d.pct || 0), fpct = Math.min(100, d.forecast_pct || 0);
        const good = (d.forecast_pct || 0) >= 100;
        $("plan-sub").textContent = `${money(d.done, d.currency)} из ${money(d.target, d.currency)}`;
        $("plan-body").innerHTML = `
            <div class="pc-big"><span class="tnum">${num(d.pct || 0, 1)}%</span><span class="badge ${good ? "closed" : "paid"} plain">${good ? "успеваете" : "отстаёте от плана"}</span></div>
            <div class="pc-bar" title="Прогноз на конец месяца: ${esc(money(d.forecast, d.currency))}"><i style="width:${pct}%"></i><b style="left:${fpct}%"></b></div>
            <div class="pc-rows">
                <div><span class="k">Прогноз на конец месяца</span><span class="v tnum">${money(Math.round(d.forecast), d.currency)}</span></div>
                <div><span class="k">${d.done >= d.target ? "План выполнен" : `Чтобы успеть, в день`}</span><span class="v tnum">${d.done >= d.target ? "🎉" : money(Math.ceil(d.per_day), d.currency)}</span></div>
                <div><span class="k">Осталось дней</span><span class="v tnum">${d.days_left}</span></div>
                ${d.profit ? `<div><span class="k">Чистая прибыль за месяц</span><span class="v tnum">${money(d.profit.profit, d.currency)}</span></div>` : ""}
            </div>`;
    }
    function bindPlan(alive, target) {
        const b = $("plan-set");
        if (b) b.addEventListener("click", () => planSheet(target));
        if (target) fillPlan(alive);
    }
    function planSheet(target) {
        haptic();
        const sh = openSheet(`<div class="detail">
            <div class="head"><div class="ic tint-brand" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("trend")}</div>
                <div style="flex:1;min-width:0"><div class="title">План продаж на месяц</div><div class="sub">Выручка в рублях, без возвратов</div></div></div>
            <div class="list"><div class="field"><label for="pl-v">Сколько хотите заработать за ${MONTHS_NOM[new Date().getMonth()]}, ₽</label>
                <input type="number" inputmode="decimal" id="pl-v" min="0" step="100" value="${target || ""}" placeholder="например, 50000">
                <div class="hint">0 — убрать план. Прогноз считается по темпу продаж с начала месяца.</div></div></div>
            <div style="margin-top:14px"><button class="btn" id="pl-save">${icon("check")}Сохранить</button></div></div>`);
        sh.querySelector("#pl-save").addEventListener("click", async (e) => {
            e.currentTarget.disabled = true;
            try {
                await api("/api/plan", { method: "POST", body: { amount: sh.querySelector("#pl-v").value || 0 } });
                notify("success"); toast("План сохранён"); closeSheet(); render(true);
            } catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
        });
    }
    // ---------- обновление Cardinal Plus (из релизов на GitHub) ----------
    const updBanner = (u) => u && u.available ? `<button class="banner upd-banner" id="upd-banner"><div class="ring">${icon("refresh")}</div>
        <div class="grow"><div class="t">Вышла Cardinal Plus ${esc(u.version)}</div><div class="s">Нажмите, чтобы обновить — настройки и плагины сохранятся</div></div>
        <div class="chev">${icon("chevron")}</div></button>` : "";
    const updWait = (text) => `<div class="empty" style="padding:24px 12px 12px"><div class="e spin">${icon("refresh")}</div><div class="h">${esc(text)}</div>Не закрывайте Cardinal на компьютере.</div>`;
    async function updateSheet() {
        haptic();
        const sh = openSheet(`<div class="head"><div class="ic tint-brand">${icon("refresh")}</div><div style="flex:1;min-width:0"><div class="title">Обновление Cardinal Plus</div>
            <div class="sub" id="up-sub">Проверяю, есть ли новая версия…</div></div></div><div id="up-body">${updWait("Спрашиваю GitHub…").replace("Не закрывайте Cardinal на компьютере.", "")}</div>`);
        let st;
        try { st = await api("/api/plus/update?check=1"); }
        catch (e) { const b = sh.querySelector("#up-body"); if (b) b.innerHTML = errorBox(e); return; }
        drawUpdate(sh, st);
    }
    function drawUpdate(sh, st) {
        const body = sh.querySelector("#up-body"), sub = sh.querySelector("#up-sub");
        if (!body || !sh.isConnected) return;
        sub.textContent = `У вас версия ${st.version}`;
        if (!st.configured) {
            body.innerHTML = `<div class="plugin-desc">В этой сборке проверка обновлений не настроена. Новую версию Cardinal Plus скачайте там же, где взяли эту.</div>`;
            return;
        }
        if (st.busy) return followUpdate(sh, st);
        if (st.available) {
            const L = st.latest, when = L.published ? new Date(L.published).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : "";
            body.innerHTML = `<div class="up-card"><div class="up-v">Вышла версия ${esc(L.version)}</div>${when ? `<div class="up-d">${esc(when)}</div>` : ""}
                    ${L.notes ? `<div class="up-notes">${esc(L.notes)}</div>` : ""}</div>
                <button class="btn" id="up-go">${icon("refresh")}<span>Обновить до ${esc(L.version)}</span></button>
                <div class="note">Cardinal сам скачает новую версию, сохранит копию текущей и перезапустится — это займёт около минуты. Настройки, ключи и плагины не тронутся.</div>`;
            body.querySelector("#up-go").addEventListener("click", async () => {
                if (!(await confirmDialog(`Обновить Cardinal Plus до ${L.version}? Cardinal перезапустится, приложение нужно будет открыть заново.`))) return;
                haptic("medium");
                let r;
                try { r = await api("/api/plus/update", { method: "POST", body: {} }); }
                catch (e) { toast(e.message, "err"); notify("error"); return; }
                followUpdate(sh, r);
            });
            return;
        }
        body.innerHTML = st.error
            ? `<div class="warn-box">${icon("alert")}<div>${esc(st.error)}</div></div>`
            : `<div class="empty" style="padding:18px 12px 8px"><div class="e">${icon("check")}</div><div class="h">У вас последняя версия</div>Cardinal Plus ${esc(st.version)}</div>`;
    }
    async function followUpdate(sh, st) {
        const body = sh.querySelector("#up-body");
        const to = st.latest ? st.latest.version : "";
        body.innerHTML = updWait(st.stage_text || "Скачиваю обновление…");
        for (let i = 0; i < 400; i++) {           // до ~9 минут: вдруг ставятся новые библиотеки
            await new Promise((r) => setTimeout(r, 1400));
            if (!sh.isConnected) return;           // окно закрыли — обновление идёт дальше само
            try { st = await api("/api/plus/update"); } catch (e) { break; }   // сервер ушёл на перезапуск
            if (st.stage === "restart" || st.result) break;
            if (!st.busy) {
                body.innerHTML = `<div class="warn-box">${icon("alert")}<div>${esc(st.error || "Обновление не удалось.")}<br>Ничего не сломалось — работает прежняя версия.</div></div>`;
                notify("error");
                return;
            }
            body.innerHTML = updWait(st.stage_text || "Обновляю…");
        }
        notify("success");
        body.innerHTML = `<div class="empty" style="padding:24px 12px 12px"><div class="e">${icon("check")}</div><div class="h">Cardinal Plus ${esc((st.result && st.result.to) || to)} установлен</div>${inTelegram
                ? "Cardinal перезапускается. Через полминуты откройте приложение заново кнопкой в боте."
                : "Cardinal перезапускается. Через полминуты отправьте боту <code>/web</code> и войдите по новой ссылке."}</div>
            ${inTelegram ? `<button class="btn" id="up-close">Закрыть приложение</button>` : ""}`;
        const c = body.querySelector("#up-close");
        if (c) c.addEventListener("click", () => { try { tg.close(); } catch (e) {} });
    }
    const guardBanner = (g) => g && g.enabled && g.state === "down" ? `<div class="banner guard-banner"><div class="ring">${icon("alert")}</div>
        <div class="grow"><div class="t">Нет связи с FunPay${g.down_since ? ` с ${hm(new Date(g.down_since * 1000))}` : ""}</div><div class="s">${esc(g.reason || "")}</div></div></div>` : "";

    // ---------- Отзывы ----------
    let reviewsFilter = "", reviewsQuery = "";
    async function renderReviews(screen, alive) {
        const desk = isDesktop();
        const right = `<div style="display:flex;gap:8px"><button class="btn-sm" id="rv-fetch" title="Проверить последние завершённые заказы на FunPay">${icon("history")}${isDesktop() ? "<span>Загрузить старые</span>" : ""}</button>
            <button class="icon-btn" id="rv-reload" aria-label="Обновить">${icon("refresh")}</button></div>`;
        if (!screen.keep) paint(pageHead("Отзывы", "", right) + sk(110) + sk(150) + sk(150));
        let d;
        try { d = await api(`/api/reviews?filter=${encodeURIComponent(reviewsFilter)}&q=${encodeURIComponent(reviewsQuery)}`); }
        catch (e) { if (alive()) paint(backLink() + pageHead("Отзывы", "", right) + errorBox(e)); return; }
        if (!alive()) return;
        screen.keep = false;
        const job = d.job && d.job.running ? `<div class="note" id="rv-job">Проверяю заказы на FunPay: ${d.job.done} из ${d.job.total}, найдено отзывов: ${d.job.found}…</div>` : "";
        const sub = d.total ? `Средняя оценка ${num(d.avg, 2)} · ${d.total} ${plural(d.total, "отзыв", "отзыва", "отзывов")}` : "Отзывов пока нет";
        const chips = [["", "Все", d.total], ["bad", "Плохие", d.bad], ["noreply", "Без ответа", d.no_reply]]
            .concat(desk ? [5, 4, 3, 2, 1].map((n) => [String(n), `${n} ★`, d.stars[n]]) : []);
        const dist = [5, 4, 3, 2, 1].map((n) => { const c = d.stars[n] || 0, p = d.total ? Math.round(c / d.total * 100) : 0;
            return `<div class="rv-dist"><span>${n} ★</span><div class="track"><i class="${n <= 3 ? "bad" : ""}" style="width:${p}%"></i></div><b class="tnum">${c}</b></div>`; }).join("");
        const summary = desk ? `
            <div class="kpis">
                <div class="kpi"><div class="h"><div class="ic tint-amber">${icon("star")}</div>Средняя оценка</div><div class="v tnum">${d.avg ? num(d.avg, 2) : "—"}</div><div class="f">${d.avg ? starsHtml(Math.round(d.avg)) : "пока нет отзывов"}</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-blue">${icon("history")}</div>За 30 дней</div><div class="v tnum">${d.month.count}</div><div class="f">${d.month.avg ? `средняя ${num(d.month.avg, 2)}` : "новых не было"}</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-red">${icon("alert")}</div>Плохие (1–3 ★)</div><div class="v tnum ${d.bad ? "red-t" : ""}">${d.bad}</div><div class="f">${d.total ? `${Math.round(d.bad / d.total * 100)}% всех отзывов` : ""}</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-violet">${icon("chat")}</div>Без ответа</div><div class="v tnum">${d.no_reply}</div><div class="f">${d.no_reply ? `<button class="btn-sm" data-rf="noreply" style="padding:4px 9px;font-size:12.5px">Показать</button>` : "на все отзывы есть ответ"}</div></div>
            </div>
            ${d.total ? `<div class="panel" style="margin-bottom:14px"><div class="panel-h"><div class="ic tint-amber">${icon("chart")}</div><div><div class="t">Оценки</div><div class="s">сколько отзывов с каждой оценкой</div></div></div>${dist}</div>` : ""}`
            : (d.total ? `<div class="rv-sum"><div class="big tnum">${num(d.avg, 1)}</div><div>${starsHtml(Math.round(d.avg))}<div class="s">${d.total} ${plural(d.total, "отзыв", "отзыва", "отзывов")} · плохих ${d.bad} · без ответа ${d.no_reply}</div></div></div>` : "");
        const card = (r) => `
            <div class="rv-card ${r.stars <= 3 ? "bad" : ""}" data-oid="${esc(r.order_id)}">
                <div class="rv-h">${buyerAvatar(r.buyer)}<div class="body"><div class="t"><span class="txt">${esc(r.buyer || "Покупатель")}</span>${starsHtml(r.stars)}</div>
                    <div class="s">${tsDay(r.first_seen)} · #${esc(r.order_id)}${r.title ? ` · ${esc(r.title)}` : ""}</div></div></div>
                <div class="rv-text">${r.text ? esc(r.text) : `<span class="muted">Без текста</span>`}</div>
                ${r.reply ? `<div class="rv-reply"><div class="l">Ваш ответ</div>${esc(r.reply)}</div>` : ""}
                <div class="rv-acts">
                    <button class="btn-sm ${r.reply ? "" : "primary"}" data-rv-reply="${esc(r.order_id)}">${icon(r.reply ? "pencil" : "chat")}<span>${r.reply ? "Изменить ответ" : "Ответить"}</span></button>
                    ${r.reply ? `<button class="btn-sm" data-rv-del="${esc(r.order_id)}">${icon("trash")}<span class="hide-xs">Удалить ответ</span></button>` : ""}
                    <span class="grow"></span>
                    <button class="icon-btn" data-rv-chat="${esc(r.order_id)}" title="Чат с покупателем">${icon("chat")}</button>
                    <button class="icon-btn" data-link-o="${esc(r.order_id)}" title="Заказ на FunPay">${icon("external")}</button>
                </div>
            </div>`;
        paint(`${backLink()}${pageHead("Отзывы", esc(sub), right)}${job}${summary}
            <div class="${desk ? "toolbar" : ""}">
                <label class="search">${icon("search")}<input id="rv-q" type="search" placeholder="Ник, текст или номер заказа" value="${esc(reviewsQuery)}" autocomplete="off"></label>
                <div class="chips">${chips.map(([v, l, n]) => `<button class="chip ${v === reviewsFilter ? "active" : ""}" data-rf="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
            </div>
            ${d.items.length ? `<div class="${desk ? "rv-grid" : ""}">${d.items.map(card).join("")}</div>`
                : d.total ? emptyBox("search", "Ничего не нашлось", "Попробуйте другой фильтр")
                : emptyBox("star", "Отзывов пока нет", "Новые отзывы появятся здесь сами. Старые можно загрузить кнопкой «Загрузить старые» — я проверю последние завершённые заказы.")}`);
        const byId = Object.fromEntries(d.items.map((r) => [r.order_id, r]));
        $view.querySelectorAll("[data-rf]").forEach((b) => b.addEventListener("click", () => { haptic("light"); reviewsFilter = b.dataset.rf; screen.keep = true; renderReviews(screen, alive); }));
        let qt;
        $("rv-q").addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { reviewsQuery = e.target.value; screen.keep = true; renderReviews(screen, alive).then(() => { const i = $("rv-q"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 350); });
        $("rv-reload").addEventListener("click", () => { haptic(); render(); });
        $("rv-fetch").addEventListener("click", async (e) => {
            e.currentTarget.disabled = true;
            try {
                const r = await api("/api/reviews/fetch", { method: "POST", body: { limit: 40 } });
                toast(r.job.total ? `Проверяю заказы: ${r.job.total}` : "Все последние заказы уже проверены");
                if (r.job.total) pollReviewsJob(alive, screen);
            } catch (err) { toast(err.message, "err"); }
            finally { const b = $("rv-fetch"); if (b) b.disabled = false; }
        });
        $view.querySelectorAll("[data-rv-reply]").forEach((b) => b.addEventListener("click", () => reviewReplySheet(byId[b.dataset.rvReply], () => { screen.keep = true; renderReviews(screen, alive); })));
        $view.querySelectorAll("[data-rv-del]").forEach((b) => b.addEventListener("click", async () => {
            if (!(await confirmDialog("Удалить ваш ответ на этот отзыв на FunPay?"))) return;
            try { await api("/api/reviews/reply", { method: "POST", body: { order_id: b.dataset.rvDel, delete: true } }); toast("Ответ удалён"); screen.keep = true; renderReviews(screen, alive); }
            catch (err) { toast(err.message, "err"); }
        }));
        $view.querySelectorAll("[data-rv-chat]").forEach((b) => b.addEventListener("click", () => { const r = byId[b.dataset.rvChat]; openChatByName(r.buyer, r.chat_id); }));
        $view.querySelectorAll("[data-link-o]").forEach((b) => b.addEventListener("click", () => openLink(`https://funpay.com/orders/${b.dataset.linkO}/`)));
        if (d.job && d.job.running) pollReviewsJob(alive, screen);
    }
    function pollReviewsJob(alive, screen) {
        const t = setInterval(async () => {
            if (!alive()) return clearInterval(t);
            try {
                const d = await api("/api/reviews?filter=x");
                const el = $("rv-job");
                if (d.job && d.job.running) { if (el) el.textContent = `Проверяю заказы на FunPay: ${d.job.done} из ${d.job.total}, найдено отзывов: ${d.job.found}…`; return; }
                clearInterval(t);
                if (d.job) toast(`Готово: найдено отзывов — ${d.job.found}`);
                screen.keep = true; renderReviews(screen, alive);
            } catch (e) { clearInterval(t); }
        }, 2000);
        chatTimers.push(t);
    }
    function reviewReplySheet(r, onDone) {
        haptic();
        const sh = openSheet(`<div class="detail">
            <div class="head"><div style="flex:1;min-width:0"><div class="title">${r.reply ? "Изменить ответ" : "Ответ на отзыв"} ${starsHtml(r.stars)}</div><div class="sub">${esc(r.buyer)} · заказ #${esc(r.order_id)}</div></div></div>
            <div class="rv-quote">${r.text ? esc(r.text) : "Без текста"}</div>
            <div class="list"><div class="field"><label for="rr-t">Ваш ответ — его увидят все на FunPay</label>
                <textarea id="rr-t" rows="5" maxlength="999" placeholder="Например: Спасибо за отзыв! Разберёмся и всё исправим.">${esc(r.reply || "")}</textarea>
                <div class="hint"><span id="rr-n">${(r.reply || "").length}</span> / 999</div></div></div>
            <div style="margin-top:14px"><button class="btn" id="rr-save">${icon("send")}Опубликовать</button></div></div>`);
        const ta = sh.querySelector("#rr-t");
        ta.addEventListener("input", () => { sh.querySelector("#rr-n").textContent = ta.value.length; });
        setTimeout(() => ta.focus(), 250);
        sh.querySelector("#rr-save").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            if (!ta.value.trim()) { toast("Напишите ответ", "err"); return; }
            btn.disabled = true;
            try { await api("/api/reviews/reply", { method: "POST", body: { order_id: r.order_id, text: ta.value } }); notify("success"); toast("Ответ опубликован"); closeSheet(); onDone(); }
            catch (err) { toast(err.message, "err"); notify("error"); btn.disabled = false; }
        });
    }

    // ---------- Покупатели (Панель) ----------
    let buyersData = null, buyersQ = "", buyersSort = "spent", buyersFlt = "", buyersMore = 1;
    async function renderBuyers(screen, alive, refresh) {
        const head = (sub) => pageHead("Покупатели", sub, `<button class="icon-btn" id="by-reload" title="Загрузить заново с FunPay">${icon("refresh")}</button>`);
        if (!buyersData || refresh === true) {
            paint(head(`<span id="by-progress">Загружаю заказы за год с FunPay…</span>`) + `<div class="kpis">${sk(108, 0).repeat(4)}</div>` + sk(420));
            $("by-reload").addEventListener("click", () => { buyersData = null; render(true); });
            try { buyersData = await loadReady(`/api/buyers${refresh === true ? "?refresh=1" : ""}`, alive, (p) => { const el = $("by-progress"); if (el) el.textContent = `Загружаю заказы за год с FunPay… страниц: ${p}`; }); }
            catch (e) { if (alive()) paint(head("") + errorBox(e)); return; }
            if (!buyersData) return;
        }
        const all = buyersData.buyers;
        const repeat = all.filter((b) => b.repeat).length;
        const rubTotal = all.reduce((s, b) => s + (b.spent["₽"] || 0), 0);
        const blCount = all.filter((b) => b.blacklisted).length;
        const flt = { repeat: (b) => b.repeat, bad: (b) => b.reviews && b.reviews.bad, refunds: (b) => b.refunds > 0, bl: (b) => b.blacklisted };
        const sorters = { spent: (a, b) => (b.spent["₽"] || 0) - (a.spent["₽"] || 0), orders: (a, b) => b.orders - a.orders, last: (a, b) => String(b.last || "").localeCompare(String(a.last || "")) };
        const draw = () => {
            const q = buyersQ.trim().toLowerCase();
            const list = all.filter((b) => (!buyersFlt || flt[buyersFlt](b)) && (!q || b.name.toLowerCase().includes(q) || String(b.favorite || "").toLowerCase().includes(q))).sort(sorters[buyersSort]);
            const shown = list.slice(0, 100 * buyersMore);
            const spent = (b) => Object.entries(b.spent).map(([c, v]) => money(v, c)).join(" · ") || "—";
            $("by-table").innerHTML = list.length ? `<div class="table-wrap"><table class="table by-table"><thead><tr><th>Покупатель</th><th class="num">Заказов</th><th class="num">Потратил</th><th class="num">Возвраты</th><th>Отзывы</th><th class="num">Первый</th><th class="num">Последний</th><th>Чаще покупает</th></tr></thead><tbody>
                ${shown.map((b, i) => `<tr data-bi="${all.indexOf(b)}"><td><div class="who">${buyerAvatar(b.name)}<span class="desc">${esc(b.name)}</span>${b.blacklisted ? `<span class="badge refunded plain">ЧС</span>` : ""}${b.repeat ? `<span class="badge closed plain">постоянный</span>` : ""}</div></td>
                    <td class="num tnum">${b.orders}</td><td class="num tnum">${spent(b)}</td><td class="num ${b.refunds ? "red-t" : "muted"}">${b.refunds || "—"}</td>
                    <td>${b.reviews ? `${starsHtml(Math.round(b.reviews.avg), "sm")} <span class="muted">${b.reviews.count}</span>` : `<span class="muted">—</span>`}</td>
                    <td class="num muted">${b.first ? new Date(b.first).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "2-digit" }) : ""}</td>
                    <td class="num">${b.last ? shortTime(b.last) : ""}</td><td><div class="desc fav" title="${esc(b.favorite || "")}">${esc(b.favorite || "")}</div></td></tr>`).join("")}
                </tbody></table></div>${list.length > shown.length ? `<button class="btn secondary" id="by-more" style="max-width:280px;margin:12px auto 0">Показать ещё (${list.length - shown.length})</button>` : ""}`
                : emptyBox("search", "Никого не нашлось", "Попробуйте другой запрос или фильтр");
            $("by-count").textContent = list.length !== all.length ? `найдено ${list.length}` : "";
            $view.querySelectorAll("tr[data-bi]").forEach((tr) => tr.addEventListener("click", () => buyerSheet(all[+tr.dataset.bi], draw)));
            const more = $("by-more"); if (more) more.addEventListener("click", () => { buyersMore++; draw(); });
        };
        const sortChips = [["spent", "По сумме"], ["orders", "По заказам"], ["last", "Недавние"]];
        const fltChips = [["", "Все", all.length], ["repeat", "Постоянные", repeat], ["bad", "С плохими отзывами", all.filter(flt.bad).length], ["refunds", "С возвратами", all.filter(flt.refunds).length], ["bl", "В ЧС", blCount]];
        paint(`${head(`${all.length} ${plural(all.length, "покупатель", "покупателя", "покупателей")} за год${buyersData.partial ? ` · с ${new Date(buyersData.covered_from).toLocaleDateString("ru-RU")}` : ""}`)}
            <div class="kpis">
                <div class="kpi"><div class="h"><div class="ic tint-blue">${icon("users")}</div>Покупателей</div><div class="v tnum">${num(all.length, 0)}</div><div class="f">за последний год</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-green">${icon("restore")}</div>Вернулись снова</div><div class="v tnum">${repeat}</div><div class="f">${all.length ? Math.round(repeat / all.length * 100) : 0}% покупают повторно</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-brand">${icon("coins")}</div>В среднем на покупателя</div><div class="v tnum">${money(all.length ? Math.round(rubTotal / all.length) : 0)}</div><div class="f">всего ${money(Math.round(rubTotal))}</div></div>
                <div class="kpi"><div class="h"><div class="ic tint-red">${icon("ban")}</div>В чёрном списке</div><div class="v tnum">${blCount}</div><div class="f"><button class="btn-sm" id="by-bl" style="padding:4px 9px;font-size:12.5px">Чёрный список</button></div></div>
            </div>
            <div class="toolbar">
                <label class="search">${icon("search")}<input id="by-q" type="search" placeholder="Ник или товар" value="${esc(buyersQ)}" autocomplete="off"></label>
                <div class="chips">${fltChips.map(([v, l, n]) => `<button class="chip ${v === buyersFlt ? "active" : ""}" data-bf="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
            </div>
            <div class="by-sort"><span class="muted">Сортировка:</span>${sortChips.map(([v, l]) => `<button class="link-btn ${v === buyersSort ? "on" : ""}" data-bs="${v}">${l}</button>`).join("")}<span class="grow"></span><span class="muted" id="by-count"></span></div>
            <div class="panel" id="by-table"></div>`);
        draw();
        $("by-reload").addEventListener("click", () => { buyersData = null; render(true); });
        $("by-bl").addEventListener("click", () => push({ type: "blacklist" }));
        $("by-q").addEventListener("input", (e) => { buyersQ = e.target.value; buyersMore = 1; draw(); });
        $view.querySelectorAll("[data-bf]").forEach((b) => b.addEventListener("click", () => { buyersFlt = b.dataset.bf; buyersMore = 1; $view.querySelectorAll("[data-bf]").forEach((x) => x.classList.toggle("active", x === b)); draw(); }));
        $view.querySelectorAll("[data-bs]").forEach((b) => b.addEventListener("click", () => { buyersSort = b.dataset.bs; $view.querySelectorAll("[data-bs]").forEach((x) => x.classList.toggle("on", x === b)); draw(); }));
    }
    function buyerSheet(b, redraw) {
        haptic();
        const spent = Object.entries(b.spent).map(([c, v]) => money(v, c)).join(" · ") || "—";
        const sh = openSheet(`<div class="detail">
            <div class="head">${buyerAvatar(b.name)}<div style="flex:1;min-width:0"><div class="title">${esc(b.name)}</div><div class="sub">${b.blacklisted ? "В чёрном списке" : b.repeat ? "Постоянный покупатель" : "Покупатель"}</div></div></div>
            <div class="list">
                <div class="kv-row"><span class="k">Заказов</span><span class="v tnum">${b.orders}${b.refunds ? ` · возвратов ${b.refunds}` : ""}</span></div>
                <div class="kv-row"><span class="k">Потратил</span><span class="v tnum">${spent}</span></div>
                <div class="kv-row"><span class="k">Первая покупка</span><span class="v">${b.first ? fullDate(b.first) : "—"}</span></div>
                <div class="kv-row"><span class="k">Последняя</span><span class="v">${b.last ? fullDate(b.last) : "—"}</span></div>
                ${b.favorite ? `<div class="kv-row"><span class="k">Чаще покупает</span><span class="v">${esc(b.favorite)}</span></div>` : ""}
                <div class="kv-row"><span class="k">Отзывы</span><span class="v">${b.reviews ? `${starsHtml(Math.round(b.reviews.avg), "sm")} ${num(b.reviews.avg, 1)} · ${b.reviews.count}${b.reviews.bad ? ` · плохих ${b.reviews.bad}` : ""}` : "нет"}</span></div>
            </div>
            <div style="margin-top:14px;display:grid;gap:8px">
                <button class="btn" id="bs-chat">${icon("chat")}Открыть чат</button>
                ${b.id ? `<button class="btn secondary" id="bs-prof">${icon("external")}Профиль на FunPay</button>` : ""}
                <button class="btn ${b.blacklisted ? "secondary" : "danger"}" id="bs-bl">${icon(b.blacklisted ? "check" : "userx")}${b.blacklisted ? "Убрать из чёрного списка" : "В чёрный список"}</button>
            </div></div>`);
        sh.querySelector("#bs-chat").addEventListener("click", () => { closeSheet(true); openChatByName(b.name); });
        const pr = sh.querySelector("#bs-prof"); if (pr) pr.addEventListener("click", () => openLink(`https://funpay.com/users/${b.id}/`));
        sh.querySelector("#bs-bl").addEventListener("click", async () => {
            if (!b.blacklisted && !(await confirmDialog(`Добавить ${b.name} в чёрный список?`))) return;
            try { await blacklistChange(b.blacklisted ? "remove" : "add", b.name); b.blacklisted = !b.blacklisted; closeSheet(); redraw(); }
            catch (e) { toast(e.message, "err"); }
        });
    }

    // ---------- себестоимость (Статистика) ----------
    function costsSheet(d, onSaved) {
        haptic();
        const costs = { ...(d.costs.costs || {}) };
        const titles = [...new Set([...(d.titles || []), ...Object.keys(costs)])];
        const sh = openSheet(`<div class="detail">
            <div class="head"><div class="ic tint-green" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("coins")}</div>
                <div style="flex:1;min-width:0"><div class="title">Себестоимость</div><div class="sub">Сколько вам стоит 1 штука — из этого считается чистая прибыль</div></div></div>
            <div class="list" style="margin-bottom:10px"><div class="field"><label for="cs-pct">Для товаров без своей цены: % от цены продажи</label>
                <input type="number" inputmode="decimal" id="cs-pct" min="0" max="100" step="1" value="${d.costs.default_pct || ""}" placeholder="0 — не считать">
                <div class="hint">Например, 60 — если закупаете примерно за 60% от цены. 0 — такие товары в прибыль не попадают.</div></div></div>
            <label class="search">${icon("search")}<input id="cs-q" type="search" placeholder="Найти товар" autocomplete="off"></label>
            <div class="list cs-list" id="cs-list"></div>
            <div style="margin-top:14px"><button class="btn" id="cs-save">${icon("check")}Сохранить</button></div></div>`);
        const draw = () => {
            const q = sh.querySelector("#cs-q").value.trim().toLowerCase();
            sh.querySelector("#cs-list").innerHTML = titles.filter((t) => !q || t.toLowerCase().includes(q)).slice(0, 150).map((t) => `
                <div class="item no-icon cs-row"><div class="body"><div class="t"><span class="txt" title="${esc(t)}">${esc(t)}</span></div></div>
                    <input type="number" inputmode="decimal" min="0" step="any" data-ct="${esc(t)}" value="${costs[t] ?? ""}" placeholder="₽ за шт."></div>`).join("") || `<div class="empty-sm">Нет товаров</div>`;
            sh.querySelectorAll("[data-ct]").forEach((inp) => inp.addEventListener("input", () => { costs[inp.dataset.ct] = inp.value; }));
        };
        draw();
        sh.querySelector("#cs-q").addEventListener("input", draw);
        sh.querySelector("#cs-save").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            try {
                const pct = sh.querySelector("#cs-pct").value || 0;
                if (Number(pct) !== Number(d.costs.default_pct || 0)) await api("/api/costs", { method: "POST", body: { default_pct: pct } });
                for (const t of titles) {
                    const was = (d.costs.costs || {})[t], now = costs[t];
                    if (String(was ?? "") !== String(now ?? "")) await api("/api/costs", { method: "POST", body: { title: t, cost: now === "" ? null : now } });
                }
                notify("success"); toast("Себестоимость сохранена"); closeSheet(); onSaved();
            } catch (err) { toast(err.message, "err"); btn.disabled = false; }
        });
    }

    // ---------- Расписание лотов ----------
    const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
    function daysLabel(days) {
        const s = [...days].sort().join(",");
        if (s === "0,1,2,3,4,5,6") return "каждый день";
        if (s === "0,1,2,3,4") return "по будням";
        if (s === "5,6") return "по выходным";
        return days.map((d) => DAYS[d]).join(", ");
    }
    async function renderSchedule(screen, alive) {
        const head = () => backLink() + pageHead(isDesktop() ? "Расписание лотов" : "Расписание", "Лоты сами включаются и выключаются по времени", `<button class="btn-sm primary" id="sc-new">${icon("plus")}<span>Новое</span></button>`);
        paint(head() + sk(96) + sk(96));
        let d;
        try { d = await api("/api/lots/schedule"); } catch (e) { if (alive()) paint(head() + errorBox(e)); return; }
        if (!alive()) return;
        const rules = d.rules;
        paint(`${head()}
            ${rules.length ? `<div class="sc-list">${rules.map((r) => `
                <div class="sc-card ${r.enabled ? "" : "off"}" data-rule="${esc(r.id)}" role="button">
                    <div class="sc-time"><b class="tnum">${esc(r.on)}</b><span>—</span><b class="tnum">${esc(r.off)}</b></div>
                    <div class="body"><div class="t">${esc(r.name)}</div>
                        <div class="s">${daysLabel(r.days)} · ${r.lots.length} ${plural(r.lots.length, "лот", "лота", "лотов")}${r.enabled ? ` · <span class="badge ${r.now_on ? "closed" : "paid"} plain">сейчас ${r.now_on ? "включены" : "выключены"}</span>` : ""}</div></div>
                    <span data-stop>${sw(`data-sc-toggle="${esc(r.id)}"`, r.enabled)}</span>
                </div>`).join("")}</div>`
                : emptyBox("clock", "Расписаний пока нет", "Например: лоты работают с 08:00 до 23:00, а ночью выключены — чтобы не получать заказы, когда вы спите.")}
            ${d.log.length ? `${sectionHead("Последние изменения")}<div class="list">${d.log.map((l) => `<div class="item"><div class="ic tint-${l.action === "on" ? "green" : "gray"}">${icon(l.action === "on" ? "check" : "pause")}</div>
                <div class="body"><div class="t">${esc(l.rule)}: ${l.action === "on" ? "включено" : "выключено"} ${l.ok} ${plural(l.ok, "лот", "лота", "лотов")}</div><div class="s">${tsFull(l.t)}${l.failed ? ` · не получилось: ${l.failed}` : ""}</div></div></div>`).join("")}</div>` : ""}
            <div class="note">Лоты меняются только в момент начала и конца окна. Если вы вручную включите лот ночью, расписание не будет выключать его снова до следующего вечера.</div>`);
        $("sc-new").addEventListener("click", () => scheduleEditor(null, () => render()));
        $view.querySelectorAll("[data-rule]").forEach((el) => el.addEventListener("click", (e) => {
            if (e.target.closest("[data-stop]")) return;
            scheduleEditor(rules.find((r) => r.id === el.dataset.rule), () => render());
        }));
        $view.querySelectorAll("[data-sc-toggle]").forEach((inp) => inp.addEventListener("change", async () => {
            inp.disabled = true;
            try { await api("/api/lots/schedule", { method: "POST", body: { action: "toggle", id: inp.dataset.scToggle, enabled: inp.checked } }); toast(inp.checked ? "Расписание включено" : "Расписание выключено"); render(); }
            catch (e) { inp.checked = !inp.checked; toast(e.message, "err"); inp.disabled = false; }
        }));
    }
    async function scheduleEditor(rule, onSaved) {
        haptic();
        const r = rule ? { ...rule, days: [...rule.days], lots: [...rule.lots] } : { name: "", on: "08:00", off: "23:00", days: [0, 1, 2, 3, 4, 5, 6], lots: [] };
        const sh = openSheet(`<div class="detail" id="sce">${sk(50)}${sk(200)}</div>`);
        let games;
        try { games = (lotsData || await api("/api/lots")).games; lotsData = lotsData || { games }; }
        catch (e) { sh.querySelector("#sce").innerHTML = errorBox(e); return; }
        const flat = allLots(games);
        const picked = new Set(r.lots);
        const box = sh.querySelector("#sce");
        box.innerHTML = `
            <div class="head"><div class="ic tint-blue" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("clock")}</div>
                <div style="flex:1;min-width:0"><div class="title">${rule ? "Расписание" : "Новое расписание"}</div><div class="sub">В окне лоты включены, вне окна — выключены</div></div></div>
            <div class="list">
                <div class="field"><label for="sce-n">Название</label><input type="text" id="sce-n" maxlength="60" value="${esc(r.name)}" placeholder="Например: Ночью выключать"></div>
                <div class="field"><label>Лоты работают</label><div class="sce-times"><span>с</span><input type="time" id="sce-on" value="${esc(r.on)}" class="time-in"><span>до</span><input type="time" id="sce-off" value="${esc(r.off)}" class="time-in"></div>
                    <div class="hint">Можно через полночь: с 20:00 до 02:00.</div></div>
                <div class="field"><label>Дни</label><div class="sce-days">${DAYS.map((n, i) => `<button type="button" class="${r.days.includes(i) ? "on" : ""}" data-day="${i}">${n}</button>`).join("")}</div></div>
            </div>
            ${sectionHead("Какие лоты", `<span class="muted" id="sce-cnt"></span>`)}
            <label class="search">${icon("search")}<input id="sce-q" type="search" placeholder="Найти лот" autocomplete="off"></label>
            <div class="list sce-lots" id="sce-lots"></div>
            <div style="margin-top:14px;display:grid;gap:8px"><button class="btn" id="sce-save">${icon("check")}Сохранить</button>
                ${rule ? `<button class="btn danger" id="sce-del">${icon("trash")}Удалить расписание</button>` : ""}</div>`;
        const drawLots = () => {
            const q = box.querySelector("#sce-q").value.trim().toLowerCase();
            const items = flat.filter((l) => !q || `${l.title} ${l.game} ${l.sub}`.toLowerCase().includes(q)).sort((a, b) => picked.has(b.id) - picked.has(a.id));
            box.querySelector("#sce-lots").innerHTML = items.slice(0, 200).map((l) => `<label class="item no-icon sce-lot"><input type="checkbox" data-pick="${l.id}" ${picked.has(l.id) ? "checked" : ""}>
                <div class="body"><div class="t"><span class="txt">${esc(l.title)}</span></div><div class="s">${esc(l.game)} · ${esc(l.sub)}${l.active ? "" : " · выключен"}</div></div></label>`).join("") || `<div class="empty-sm">Лотов не найдено</div>`;
            box.querySelector("#sce-cnt").textContent = picked.size ? `выбрано ${picked.size}` : "";
            box.querySelectorAll("[data-pick]").forEach((c) => c.addEventListener("change", () => { picked[c.checked ? "add" : "delete"](+c.dataset.pick); box.querySelector("#sce-cnt").textContent = picked.size ? `выбрано ${picked.size}` : ""; }));
        };
        drawLots();
        box.querySelector("#sce-q").addEventListener("input", drawLots);
        box.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => { haptic("light"); b.classList.toggle("on"); }));
        box.querySelector("#sce-save").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            const days = [...box.querySelectorAll("[data-day].on")].map((b) => +b.dataset.day);
            const titles = Object.fromEntries(flat.filter((l) => picked.has(l.id)).map((l) => [l.id, l.title]));
            btn.disabled = true;
            try {
                await api("/api/lots/schedule", { method: "POST", body: { action: "save", rule: { id: rule && rule.id, name: box.querySelector("#sce-n").value,
                    on: box.querySelector("#sce-on").value, off: box.querySelector("#sce-off").value, days, lots: [...picked], titles, enabled: rule ? rule.enabled : true } } });
                notify("success"); toast("Расписание сохранено — лоты переключатся в ближайшую минуту"); closeSheet(); onSaved();
            } catch (err) { toast(err.message, "err"); btn.disabled = false; }
        });
        const del = box.querySelector("#sce-del");
        if (del) del.addEventListener("click", async () => {
            if (!(await confirmDialog(`Удалить расписание «${rule.name}»? Лоты останутся как есть.`))) return;
            try { await api("/api/lots/schedule", { method: "POST", body: { action: "delete", id: rule.id } }); toast("Расписание удалено"); closeSheet(); onSaved(); }
            catch (err) { toast(err.message, "err"); }
        });
    }

    // ---------- копия лота ----------
    async function copyLotSheet(lot, onDone) {
        haptic();
        const sh = openSheet(`<div class="detail" id="cl">${sk(50)}${sk(140)}</div>`);
        let d;
        try { d = await api(`/api/lots/${lot.id}/copy`); } catch (e) { sh.querySelector("#cl").innerHTML = errorBox(e); return; }
        const box = sh.querySelector("#cl");
        box.innerHTML = `
            <div class="head"><div class="ic tint-violet" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("layers")}</div>
                <div style="flex:1;min-width:0"><div class="title">Копия лота</div><div class="sub">Новый лот с теми же описанием, картинками и настройками</div></div></div>
            <div class="list">
                ${d.has_title ? `<div class="field"><label for="cl-t">Название копии</label><input type="text" id="cl-t" maxlength="250" value="${esc(d.title)}"></div>` : ""}
                <div class="field"><label for="cl-p">Ваша цена за 1 шт.</label><input type="number" inputmode="decimal" step="any" min="0" id="cl-p" value="${esc(d.price ?? "")}"></div>
                <div class="item no-icon"><div class="body"><div class="t">Сразу включить</div><div class="s">Иначе копия будет выключенной — проверите и включите сами</div></div>${sw('id="cl-a"', false)}</div>
            </div>
            ${d.auto_delivery || d.secrets ? `<div class="note">Товары встроенной автовыдачи FunPay в копию не переносятся — иначе один товар продавался бы дважды. Добавьте их в копию на FunPay.</div>` : ""}
            <div style="margin-top:14px"><button class="btn" id="cl-go">${icon("layers")}Создать копию</button></div>`;
        box.querySelector("#cl-go").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            const t = box.querySelector("#cl-t");
            btn.disabled = true;
            try {
                await api(`/api/lots/${lot.id}/copy`, { method: "POST", body: { title: t ? t.value : null, price: box.querySelector("#cl-p").value, active: box.querySelector("#cl-a").checked } });
                notify("success"); toast("Копия создана — она появится в списке лотов"); closeSheet(); onDone();
            } catch (err) { toast(err.message, "err"); notify("error"); btn.disabled = false; }
        });
    }

    // ---------- уведомления в Telegram ----------
    async function openNotifications() {
        haptic();
        const sh = openSheet(`<div class="detail" id="nt">${sk(50)}${sk(300)}</div>`);
        let d;
        try { d = await api("/api/notifications"); } catch (e) { sh.querySelector("#nt").innerHTML = errorBox(e); return; }
        let chat = d.chats[0];
        const box = sh.querySelector("#nt");
        const draw = () => {
            box.innerHTML = `
                <div class="head"><div class="ic tint-blue" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("tg")}</div>
                    <div style="flex:1;min-width:0"><div class="title">Уведомления в Telegram</div><div class="sub">О чём Cardinal пишет в бота. Применяется сразу</div></div></div>
                ${d.chats.length > 1 ? `<div class="segmented" style="margin-bottom:12px">${d.chats.map((c) => `<button data-nc="${esc(c.id)}" class="${c.id === chat.id ? "active" : ""}">${esc(c.title)}</button>`).join("")}</div>` : ""}
                <div class="list">${d.types.map((t) => `<div class="item no-icon"><div class="body"><div class="t">${esc(t.label)}</div><div class="s">${esc(t.hint)}</div></div>${sw(`data-nt="${esc(t.code)}"`, chat.values[t.code])}</div>`).join("")}</div>
                <div class="note">Тихие часы, сторож и «покупатель ждёт ответа» — в Настройках → «Контроль и уведомления».</div>`;
            box.querySelectorAll("[data-nc]").forEach((b) => b.addEventListener("click", () => { chat = d.chats.find((c) => c.id === b.dataset.nc); draw(); }));
            box.querySelectorAll("[data-nt]").forEach((inp) => inp.addEventListener("change", async () => {
                inp.disabled = true;
                try { const r = await api("/api/notifications", { method: "POST", body: { chat: chat.id, type: inp.dataset.nt, value: inp.checked } }); inp.checked = r.value; chat.values[inp.dataset.nt] = r.value; haptic("light"); }
                catch (e) { inp.checked = !inp.checked; toast(e.message, "err"); }
                finally { inp.disabled = false; }
            }));
        };
        draw();
    }

    // ---------- резервная копия (Панель) ----------
    function backupSheet() {
        haptic();
        let file = null;
        const sh = openSheet(`<div class="detail">
            <div class="head"><div class="ic tint-green" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("shield")}</div>
                <div style="flex:1;min-width:0"><div class="title">Резервная копия Cardinal+</div><div class="sub">Настройки, golden_key и токен бота, тексты, склад, плагины и их данные — одним файлом</div></div></div>
            ${sectionHead("Создать копию")}
            <div class="list"><div class="field"><label for="bk-p1">Пароль для файла</label><input type="password" id="bk-p1" autocomplete="new-password" placeholder="Не короче 8 символов">
                <input type="password" id="bk-p2" autocomplete="new-password" placeholder="Повторите пароль" style="margin-top:8px">
                <div class="hint">В копии ключ от вашего аккаунта FunPay — без пароля её не прочитать. Пароль не восстановить, запомните его.</div></div></div>
            <div class="bk-acts"><button class="btn" id="bk-dl">${icon("upload", "flip-v")}Скачать</button><button class="btn secondary" id="bk-tg">${icon("tg")}В Telegram</button></div>
            ${sectionHead("Восстановить из копии")}
            <div class="list"><div class="field"><button class="btn secondary" id="bk-pick">${icon("upload")}<span id="bk-fname">Выбрать файл .cpbak</span></button>
                <input type="file" id="bk-file" accept=".cpbak" hidden>
                <input type="password" id="bk-rp" autocomplete="current-password" placeholder="Пароль от копии" style="margin-top:8px">
                <div class="hint" id="bk-info">Текущие файлы перед восстановлением сохранятся в storage/backups. После восстановления Cardinal перезапустится.</div></div></div>
            <div class="bk-acts"><button class="btn secondary" id="bk-check" disabled>${icon("search")}Проверить</button><button class="btn danger" id="bk-restore" disabled>${icon("restore")}Восстановить</button></div></div>`);
        const pw = () => {
            const a = sh.querySelector("#bk-p1").value, b = sh.querySelector("#bk-p2").value;
            if (a.length < 8) { toast("Пароль — не короче 8 символов", "err"); return null; }
            if (a !== b) { toast("Пароли не совпадают", "err"); return null; }
            return a;
        };
        const make = async (send, btn) => {
            const password = pw();
            if (!password) return;
            btn.disabled = true;
            try {
                const r = await api("/api/backup/make", { method: "POST", body: { password, send } });
                if (send) toast(`Копия отправлена в Telegram: ${r.files} файлов`);
                else { downloadB64(r.name, r.content); toast(`Скачано: ${r.name}`); }
                notify("success");
            } catch (e) { toast(e.message, "err"); notify("error"); }
            finally { btn.disabled = false; }
        };
        sh.querySelector("#bk-dl").addEventListener("click", (e) => make(false, e.currentTarget));
        sh.querySelector("#bk-tg").addEventListener("click", (e) => make(true, e.currentTarget));
        const fileInp = sh.querySelector("#bk-file");
        sh.querySelector("#bk-pick").addEventListener("click", () => fileInp.click());
        fileInp.addEventListener("change", () => {
            file = fileInp.files[0] || null;
            sh.querySelector("#bk-fname").textContent = file ? file.name : "Выбрать файл .cpbak";
            sh.querySelector("#bk-check").disabled = sh.querySelector("#bk-restore").disabled = !file;
        });
        const body = async () => {
            if (!file) return null;
            if (file.size > 60 * 1024 * 1024) { toast("Файл слишком большой", "err"); return null; }
            return { content: bytesToB64(await file.arrayBuffer()), password: sh.querySelector("#bk-rp").value };
        };
        sh.querySelector("#bk-check").addEventListener("click", async (e) => {
            const btn = e.currentTarget, b = await body();
            if (!b) return;
            btn.disabled = true;
            try { const r = await api("/api/backup/inspect", { method: "POST", body: b }); sh.querySelector("#bk-info").textContent = `${r.note || "Копия"}: файлов ${r.files}, плагинов ${r.plugins}, файлов настроек ${r.configs}. Пароль подходит.`; notify("success"); }
            catch (err) { toast(err.message, "err"); }
            finally { btn.disabled = false; }
        });
        sh.querySelector("#bk-restore").addEventListener("click", async (e) => {
            const btn = e.currentTarget, b = await body();
            if (!b) return;
            if (!(await confirmDialog("Заменить текущие настройки, плагины и данные файлами из копии? Cardinal сразу перезапустится."))) return;
            btn.disabled = true;
            try {
                const r = await api("/api/backup/restore", { method: "POST", body: b });
                closeSheet();
                paint(emptyBox("restore", "Восстановлено, Cardinal перезапускается", `Файлов: ${r.files}. Прежние сохранены в ${esc(r.safety)}.<br>Приложение откроется заново примерно через полминуты.`));
                setTimeout(() => location.reload(), 30000);
            } catch (err) { toast(err.message, "err"); btn.disabled = false; }
        });
    }

    // ---------- журнал действий (Панель) ----------
    let auditKind = "", auditQ = "";
    async function renderAudit(screen, alive) {
        const head = () => backLink() + pageHead("Журнал действий", "Что и когда менялось в приложении. Тексты сообщений и пароли сюда не попадают");
        if (!screen.keep) paint(head() + sk(44) + sk(400));
        let d;
        try { d = await api(`/api/audit?kind=${encodeURIComponent(auditKind)}&q=${encodeURIComponent(auditQ)}`); }
        catch (e) { if (alive()) paint(head() + errorBox(e)); return; }
        if (!alive()) return;
        screen.keep = false;
        const total = Object.values(d.counts).reduce((a, b) => a + b, 0);
        const chips = [["", "Всё", total], ...Object.entries(d.kinds).filter(([k]) => d.counts[k]).map(([k, l]) => [k, l, d.counts[k]])];
        const KIND_IC = { chats: ["chat", "blue"], lots: ["tag", "brand"], settings: ["sliders", "violet"], plugins: ["puzzle", "violet"], stock: ["inbox", "amber"], reviews: ["star", "amber"], money: ["coins", "green"], system: ["shield", "gray"], other: ["sparkle", "gray"] };
        paint(`${head()}
            <div class="toolbar"><label class="search">${icon("search")}<input id="au-q" type="search" placeholder="Поиск по журналу" value="${esc(auditQ)}" autocomplete="off"></label>
                <div class="chips">${chips.map(([v, l, n]) => `<button class="chip ${v === auditKind ? "active" : ""}" data-ak="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div></div>
            ${d.items.length ? `<div class="panel"><div class="table-wrap"><table class="table au-table"><thead><tr><th>Когда</th><th>Раздел</th><th>Что сделано</th><th>Кто</th></tr></thead><tbody>
                ${d.items.map((r) => { const [ic, tint] = KIND_IC[r.kind] || KIND_IC.other; return `<tr><td class="muted nowrap">${tsFull(r.t)}</td>
                    <td><span class="au-kind"><span class="ic tint-${tint}">${icon(ic)}</span>${esc(d.kinds[r.kind] || r.kind)}</span></td><td>${esc(r.text)}</td>
                    <td class="muted">${r.user ? `${esc(r.name || "")}${r.via ? ` · ${r.via === "browser" ? "браузер" : "Telegram"}` : ""}` : "Cardinal+"}</td></tr>`; }).join("")}
                </tbody></table></div></div>` : emptyBox("history", total ? "Ничего не нашлось" : "Журнал пока пуст", total ? "Попробуйте другой фильтр" : "Здесь появятся изменения из приложения: лоты, настройки, ответы, плагины.")}`);
        $view.querySelectorAll("[data-ak]").forEach((b) => b.addEventListener("click", () => { auditKind = b.dataset.ak; screen.keep = true; renderAudit(screen, alive); }));
        let qt;
        $("au-q").addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { auditQ = e.target.value; screen.keep = true; renderAudit(screen, alive).then(() => { const i = $("au-q"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 350); });
    }

    // ---------- Лоты ----------
    let lotsFilter = "";
    let lotsQuery = "";
    const collapsedGames = new Set();
    let lotsData = null;

    const lotMeta = (l) => [l.server, l.side, l.amount != null ? `в наличии ${num(l.amount, 0)}` : "", l.auto ? "автовыдача FunPay" : ""].filter(Boolean).join(" · ");
    const allLots = (games) => games.flatMap((g) => g.subcategories.flatMap((s) => s.lots.map((l) => ({ ...l, game: g.name, gameId: g.id, sub: s.name, subId: s.id }))));

    async function renderLots(_, alive, refresh = false) {
        const head = (sub = "", right = "") => pageHead("Лоты", sub, right);
        if (!alive()) return;
        if (!lotsData || refresh === true) paint(head("Загружаю лоты с FunPay…") + sk(44, 12, 14) + sk(36, 14, 12) + sk(260) + sk(200));
        let d;
        try { d = await api(`/api/lots${refresh ? "?refresh=1" : ""}`); }
        catch (e) { if (alive()) paint(head() + errorBox(e)); return; }
        if (!alive()) return;
        lotsData = d;

        const games = d.games;
        const flat = allLots(games);
        const activeCnt = flat.filter((l) => l.active).length;
        const right = `<div style="display:flex;gap:8px">${flat.length ? `<button class="btn-sm primary" id="bulk-all">${icon("coins")}Цены<span class="hide-xs">&nbsp;у всех</span></button>` : ""}<button class="btn-sm" id="lots-sched" title="Расписание: включать и выключать лоты по времени">${icon("clock")}${isDesktop() ? "<span>Расписание</span>" : ""}</button><button class="icon-btn" id="lots-reload" aria-label="Обновить">${icon("refresh")}</button></div>`;
        const sub = flat.length ? `${flat.length} ${plural(flat.length, "лот", "лота", "лотов")} в ${games.length} ${plural(games.length, "игре", "играх", "играх")} · активно ${activeCnt}` : "";

        const demoBanner = d.demo ? `
            <div class="banner demo-banner">
                <div class="ring" style="background:var(--violet-soft);color:var(--violet)">${icon("sparkle")}</div>
                <div class="grow"><div class="t">Демо-режим</div><div class="s">Лоты выдуманные, FunPay не меняется. Сбросится при перезапуске Cardinal.</div></div>
                <button class="btn-sm" id="demo-off">Выключить</button>
            </div>` : "";

        if (!flat.length) {
            paint(head("", right) + stockEntryHtml() + (d.errors.length ? `<div class="error-box" style="margin-bottom:12px">${icon("alert")}<div>Часть данных не загрузилась: ${esc(d.errors.join(", "))}</div></div>` : "") +
                emptyBox("tag", "Лотов не найдено", "Здесь появятся ваши лоты с FunPay.<br>Если все лоты выключены, добавьте их раздел вручную ниже.") +
                `<button class="btn" id="demo-on" style="max-width:360px;margin:0 auto">${icon("sparkle")}Попробовать на демо-лотах</button>` + addSubBlock());
            bindLotsCommon(alive);
            return;
        }

        const chips = [["", "Все", flat.length], ["on", "Активные", activeCnt], ["off", "Выключенные", flat.length - activeCnt]];
        paint(`${head(sub, right)}${demoBanner}${stockEntryHtml()}
            <div class="${isDesktop() ? "toolbar" : ""}">
                <label class="search">${icon("search")}<input id="lq" type="search" placeholder="Поиск по названию или игре" value="${esc(lotsQuery)}" autocomplete="off"></label>
                <div class="chips">${chips.map(([v, l, n]) => `<button class="chip ${v === lotsFilter ? "active" : ""}" data-lf="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
            </div>
            ${d.errors.length ? `<div class="note" style="margin:-4px 6px 12px">Не загрузилось: ${esc(d.errors.join(", "))}</div>` : ""}
            <div id="lots-list"></div>
            ${d.demo ? "" : addSubBlock() + `<div class="note" style="text-align:center;margin-top:12px"><button class="link-btn" id="demo-on">Попробовать функции на демо-лотах</button></div>`}`);

        const listEl = $("lots-list");
        const draw = () => {
            const q = lotsQuery.trim().toLowerCase();
            const match = (l, g) => (!lotsFilter || (lotsFilter === "on") === l.active) &&
                (!q || [l.title, g.name, l.server, l.side].some((x) => String(x || "").toLowerCase().includes(q)));
            const html = games.map((g) => {
                const subs = g.subcategories.map((s) => ({ ...s, lots: s.lots.filter((l) => match(l, g)) })).filter((s) => s.lots.length);
                if (!subs.length) return "";
                const collapsed = collapsedGames.has(g.id) && !q;
                return `
                    <div class="game ${collapsed ? "collapsed" : ""}" data-game="${g.id}">
                        <div class="game-h">
                            <button class="game-t" data-collapse="${g.id}">
                                <div class="g-ic" style="background:${gameGradient(g.name)}">${esc((g.name || "?")[0].toUpperCase())}</div>
                                <div style="min-width:0;flex:1"><div class="t">${esc(g.name)}</div><div class="s">активно ${g.active} из ${g.total}</div></div>
                                <span class="chev rot">${icon("chevron")}</span>
                            </button>
                            <button class="btn-sm" data-bulk-game="${g.id}">${icon("coins")}Цены</button>
                        </div>
                        <div class="game-b">
                            ${subs.map((s) => `
                                ${g.subcategories.length > 1 || s.name ? `<div class="sub-l">${esc(s.name)}</div>` : ""}
                                <div class="list">${s.lots.map((l) => `
                                    <div class="item clickable lot ${l.active ? "" : "off"}" data-lot="${l.id}" role="button">
                                        <div class="body">
                                            <div class="t"><span class="txt">${esc(l.title)}</span></div>
                                            ${lotMeta(l) ? `<div class="s">${esc(lotMeta(l))}</div>` : ""}
                                        </div>
                                        <div class="price tnum">${money(l.price, l.currency)}</div>
                                        <span data-stop>${sw(`data-lot-active="${l.id}"`, l.active)}</span>
                                    </div>`).join("")}
                                </div>`).join("")}
                        </div>
                    </div>`;
            }).join("");
            listEl.innerHTML = html || emptyBox("search", "Ничего не нашлось", "Попробуйте другой запрос или фильтр");
            buildAzIndex(listEl);

            listEl.querySelectorAll("[data-collapse]").forEach((b) => b.addEventListener("click", () => {
                const id = +b.dataset.collapse;
                if (collapsedGames.has(id)) collapsedGames.delete(id); else collapsedGames.add(id);
                b.closest(".game").classList.toggle("collapsed");
                haptic("light");
            }));
            listEl.querySelectorAll("[data-bulk-game]").forEach((b) => b.addEventListener("click", () => {
                const g = games.find((x) => x.id === +b.dataset.bulkGame);
                openBulk({ title: g.name, lots: allLots([g]) }, () => renderLots(null, alive, "silent"));
            }));
            listEl.querySelectorAll("[data-lot]").forEach((el) => el.addEventListener("click", (e) => {
                if (e.target.closest("[data-stop]")) return;
                openLotSheet(flat.find((l) => l.id === +el.dataset.lot), (upd) => {
                    if (upd.price != null) { renderLots(null, alive, "silent"); return; }  // цена на витрине пересчитается FunPay
                    const l = findLot(games, upd.id);
                    if (l) l.active = upd.active ?? l.active;
                    recount(games); draw();
                });
            }));
            listEl.querySelectorAll("[data-lot-active]").forEach((inp) => inp.addEventListener("change", async () => {
                const id = +inp.dataset.lotActive;
                haptic("medium");
                inp.disabled = true;
                const row = inp.closest(".lot");
                try {
                    const r = await api(`/api/lots/${id}`, { method: "POST", body: { active: inp.checked } });
                    inp.checked = r.active;
                    const l = findLot(games, id);
                    if (l) l.active = r.active;
                    row.classList.toggle("off", !r.active);
                    recount(games);
                    const gEl = row.closest(".game");
                    const g = games.find((x) => x.id === +gEl.dataset.game);
                    gEl.querySelector(".game-t .s").textContent = `активно ${g.active} из ${g.total}`;
                    toast(r.active ? "Лот включён" : "Лот выключен");
                } catch (e) { inp.checked = !inp.checked; toast(e.message, "err"); notify("error"); }
                finally { inp.disabled = false; }
            }));
        };
        draw();

        $view.querySelectorAll("[data-lf]").forEach((c) => c.addEventListener("click", () => {
            lotsFilter = c.dataset.lf; haptic();
            $view.querySelectorAll("[data-lf]").forEach((x) => x.classList.toggle("active", x === c));
            draw();
        }));
        $("lq").addEventListener("input", (e) => { lotsQuery = e.target.value; draw(); });
        const ba = $("bulk-all");
        if (ba) ba.addEventListener("click", () => openBulk({ title: "Все игры", lots: flat }, () => renderLots(null, alive, "silent")));
        bindLotsCommon(alive);
    }

    // ---------- алфавитный указатель (как в контактах телефона) ----------
    let azCleanup = null;
    function removeAzIndex() {
        if (azCleanup) { azCleanup(); azCleanup = null; }
    }
    function buildAzIndex(listEl) {
        removeAzIndex();
        const games = [...listEl.querySelectorAll(".game[data-game]")];
        const firstByLetter = new Map();
        games.forEach((g) => {
            const name = g.querySelector(".game-t .t")?.textContent.trim() || "";
            const letter = (name[0] || "#").toUpperCase();
            const key = /[A-ZА-ЯЁ]/.test(letter) ? letter : "#";
            if (!firstByLetter.has(key)) firstByLetter.set(key, g);
        });
        if (firstByLetter.size < 2) return;

        const letters = [...firstByLetter.keys()].sort((a, b) => a === "#" ? 1 : b === "#" ? -1 : a.localeCompare(b, "ru"));
        const bar = document.createElement("div");
        bar.className = "az-index";
        bar.innerHTML = letters.map((l) => `<button data-az="${esc(l)}">${esc(l)}</button>`).join("");
        const bubble = document.createElement("div");
        bubble.className = "az-bubble";
        document.body.append(bar, bubble);
        document.body.classList.add("has-az");

        let current = null, bubbleTimer;
        const offset = () => isDesktop() ? 80 : 12;
        const setActive = (l) => bar.querySelectorAll("[data-az]").forEach((b) => b.classList.toggle("active", b.dataset.az === l));
        const jump = (l, showBubble) => {
            const el = firstByLetter.get(l);
            if (!el) return;
            if (l !== current) haptic("light");
            current = l;
            setActive(l);
            window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - offset(), behavior: showBubble ? "auto" : "smooth" });
            if (showBubble) {
                bubble.textContent = l;
                bubble.classList.add("show");
                clearTimeout(bubbleTimer);
                bubbleTimer = setTimeout(() => bubble.classList.remove("show"), 500);
            }
        };
        const letterAt = (y) => {
            const btns = [...bar.querySelectorAll("[data-az]")];
            const hit = btns.find((b) => { const r = b.getBoundingClientRect(); return y >= r.top && y <= r.bottom; });
            if (hit) return hit.dataset.az;
            const first = btns[0].getBoundingClientRect(), last = btns[btns.length - 1].getBoundingClientRect();
            return y < first.top ? btns[0].dataset.az : y > last.bottom ? btns[btns.length - 1].dataset.az : null;
        };
        let dragging = false;
        const onDown = (e) => { dragging = true; bar.classList.add("drag"); const l = letterAt(e.clientY); if (l) jump(l, true); e.preventDefault(); bar.setPointerCapture?.(e.pointerId); };
        const onMove = (e) => { if (!dragging) return; const l = letterAt(e.clientY); if (l && l !== current) jump(l, true); };
        const onUp = () => { dragging = false; bar.classList.remove("drag"); };
        bar.addEventListener("pointerdown", onDown);
        bar.addEventListener("pointermove", onMove);
        bar.addEventListener("pointerup", onUp);
        bar.addEventListener("pointercancel", onUp);

        // подсветка буквы текущей игры при прокрутке
        let raf = 0;
        const onScroll = () => {
            if (raf || dragging) return;
            raf = requestAnimationFrame(() => {
                raf = 0;
                let active = letters[0];
                for (const l of letters) {
                    if (firstByLetter.get(l).getBoundingClientRect().top - offset() <= 40) active = l;
                }
                if (active !== current) { current = active; setActive(active); }
            });
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();

        azCleanup = () => {
            window.removeEventListener("scroll", onScroll);
            bar.remove(); bubble.remove();
            document.body.classList.remove("has-az");
        };
    }

    function findLot(games, id) {
        for (const g of games) for (const s of g.subcategories) for (const l of s.lots) if (l.id === id) return l;
        return null;
    }
    function recount(games) {
        games.forEach((g) => {
            const ls = g.subcategories.flatMap((s) => s.lots);
            g.total = ls.length; g.active = ls.filter((l) => l.active).length;
        });
    }

    function addSubBlock() {
        return `
            <details class="add-sub">
                <summary>Не видите лоты, у которых все предложения выключены?</summary>
                <div class="note" style="margin:8px 0">Список строится по разделам, где у вас есть активные лоты. Чтобы показать раздел, где всё выключено, вставьте ссылку на него: например <code>funpay.com/lots/1234/</code> или просто номер.</div>
                <div style="display:flex;gap:8px"><label class="search" style="flex:1;margin:0">${icon("tag")}<input id="sub-id" placeholder="Ссылка или номер раздела"></label><button class="btn-sm primary" id="sub-add">Добавить</button></div>
            </details>`;
    }

    function bindLotsCommon(alive) {
        bindStockEntry();
        const setDemo = async (enabled, btn) => {
            btn.disabled = true;
            try {
                await api("/api/lots/demo", { method: "POST", body: { enabled } });
                lotsFilter = ""; lotsQuery = ""; collapsedGames.clear();
                toast(enabled ? "Демо-режим включён" : "Демо-режим выключен");
                renderLots(null, alive, true);
            } catch (e) { toast(e.message, "err"); btn.disabled = false; }
        };
        const don = $("demo-on");
        if (don) don.addEventListener("click", () => { haptic(); setDemo(true, don); });
        const doff = $("demo-off");
        if (doff) doff.addEventListener("click", () => { haptic(); setDemo(false, doff); });
        const rl = $("lots-reload");
        if (rl) rl.addEventListener("click", () => { haptic(); renderLots(null, alive, true); });
        const sc = $("lots-sched");
        if (sc) sc.addEventListener("click", () => { haptic(); push({ type: "schedule" }); });
        const sa = $("sub-add");
        if (sa) sa.addEventListener("click", async () => {
            const raw = $("sub-id").value.trim();
            const m = raw.match(/lots\/(\d+)/) || raw.match(/^(\d+)$/);
            if (!m) { toast("Вставьте ссылку вида funpay.com/lots/1234/", "err"); return; }
            sa.disabled = true;
            try { await api("/api/lots/subcategory", { method: "POST", body: { id: +m[1] } }); toast("Раздел добавлен"); renderLots(null, alive, true); }
            catch (e) { toast(e.message, "err"); sa.disabled = false; }
        });
    }

    /** Окно одного лота: точная цена из редактора, цены для покупателей, вкл/выкл. */
    async function openLotSheet(lot, onChange) {
        haptic();
        const sh = openSheet(`<div class="detail" id="lot-sheet">
            <div class="head"><div style="flex:1;min-width:0"><div class="title" style="font-size:17px;line-height:1.3">${esc(lot.title)}</div><div class="sub">${esc(lot.game)} · ${esc(lot.sub)}</div></div></div>
            ${sk(58)}${sk(120)}</div>`);
        let d;
        try { d = await api(`/api/lots/${lot.id}`); }
        catch (e) { sh.querySelector("#lot-sheet").insertAdjacentHTML("beforeend", errorBox(e)); return; }
        const box = sh.querySelector("#lot-sheet");
        box.innerHTML = `
            <div class="head"><div style="flex:1;min-width:0"><div class="title" style="font-size:17px;line-height:1.3">${esc(d.title || lot.title)}</div><div class="sub">${esc(d.game || lot.game)} · ${esc(d.subcategory || lot.sub)}</div></div></div>
            <div class="list" style="margin-bottom:10px">
                <div class="item no-icon"><div class="body"><div class="t">Лот активен</div><div class="s">Выключенный лот не виден покупателям</div></div>${sw('id="ls-active"', d.active)}</div>
            </div>
            <div class="list">
                <div class="field">
                    <label for="ls-price">Ваша цена за 1 шт., ${esc(d.currency)}</label>
                    <div style="display:flex;gap:8px"><input type="number" inputmode="decimal" step="any" min="0" id="ls-price" value="${esc(d.price ?? "")}" style="flex:1"><button class="btn-sm primary" id="ls-save" style="padding:0 18px">Сохранить</button></div>
                    <div class="hint">Это цена из редактора лота — столько получите вы. Покупатель видит цену с комиссией FunPay.</div>
                </div>
                ${d.buyer_prices.length ? `<div class="field"><label>Покупатель заплатит</label>${d.buyer_prices.map((m) => `<div class="kv-row"><span class="k">${esc(m.name || "—")}</span><span class="v tnum">${money(m.price, m.currency)}</span></div>`).join("")}<div class="hint">Пересчитается после сохранения новой цены.</div></div>` : ""}
            </div>
            <div style="margin-top:14px">
                <button class="btn secondary" id="ls-open">${icon("external")}Открыть лот на FunPay</button>
                <button class="btn secondary" id="ls-edit">${icon("pencil")}Полный редактор на FunPay</button>
                <button class="btn secondary" id="ls-copy">${icon("layers")}Сделать копию лота</button>
            </div>`;
        const act = box.querySelector("#ls-active");
        act.addEventListener("change", async () => {
            act.disabled = true;
            try {
                const r = await api(`/api/lots/${lot.id}`, { method: "POST", body: { active: act.checked } });
                act.checked = r.active; onChange({ id: lot.id, active: r.active });
                toast(r.active ? "Лот включён" : "Лот выключен");
            } catch (e) { act.checked = !act.checked; toast(e.message, "err"); }
            finally { act.disabled = false; }
        });
        box.querySelector("#ls-save").addEventListener("click", async (e) => {
            const btn = e.currentTarget;
            const price = parseFloat(String(box.querySelector("#ls-price").value).replace(",", "."));
            if (!(price > 0)) { toast("Укажите цену больше нуля", "err"); return; }
            btn.disabled = true;
            try {
                const r = await api(`/api/lots/${lot.id}`, { method: "POST", body: { price } });
                notify("success"); toast(`Цена сохранена: ${money(r.price, d.currency)}`);
                onChange({ id: lot.id, price: r.price });
                closeSheet();
            } catch (err) { toast(err.message, "err"); notify("error"); }
            finally { btn.disabled = false; }
        });
        box.querySelector("#ls-open").addEventListener("click", () => openLink(lot.link));
        box.querySelector("#ls-edit").addEventListener("click", () => openLink(lot.edit_link));
        box.querySelector("#ls-copy").addEventListener("click", () => {
            closeSheet(true);
            copyLotSheet(lot, () => { lotsData = null; if (currentTab === "lots" && !stack.length) render(true); });
        });
    }

    /** Массовое изменение цен / включение лотов в игре или во всех играх. */
    function openBulk(scope, onDone) {
        haptic();
        const st = { kind: "percent", value: "", round: "2", onlyActive: false };
        const KINDS = [["percent", "На %"], ["add", "На сумму"], ["set", "Точная цена"], ["state", "Вкл / выкл"]];
        const cur = (scope.lots[0] && scope.lots[0].currency) || "₽";
        const sh = openSheet(`<div class="detail" id="bulk">
            <div class="head">
                <div class="ic tint-brand" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("coins")}</div>
                <div style="flex:1;min-width:0"><div class="title">Массовое изменение</div><div class="sub">${esc(scope.title)} · ${scope.lots.length} ${plural(scope.lots.length, "лот", "лота", "лотов")}</div></div>
            </div>
            <div class="segmented" id="b-kind" style="margin-bottom:12px">${KINDS.map(([k, l]) => `<button data-k="${k}" class="${k === st.kind ? "active" : ""}">${l}</button>`).join("")}</div>
            <div class="list" id="b-form"></div>
            <div class="list" style="margin-top:10px"><div class="item no-icon"><div class="body"><div class="t">Только активные лоты</div><div class="s">Не трогать выключенные</div></div>${sw('id="b-only"', false)}</div></div>
            ${sectionHead("Предпросмотр", `<span class="cap" style="color:var(--muted);font-size:12.5px" id="b-count"></span>`)}
            <div class="list" id="b-preview"></div>
            <div class="note" id="b-note">Цены считаются от вашей цены в редакторе лота (без комиссии FunPay). Знак ≈ — оценка, точное значение посчитается при применении.</div>
            <div style="margin-top:14px"><button class="btn" id="b-apply">${icon("check")}<span>Применить</span></button></div>
        </div>`);

        const targets = () => scope.lots.filter((l) => !st.onlyActive || l.active);
        const calc = (p) => {
            const v = parseFloat(String(st.value).replace(",", "."));
            if (isNaN(v)) return null;
            let n = st.kind === "set" ? v : st.kind === "percent" ? p * (1 + v / 100) : p + v;
            if (st.round === "int") n = Math.max(1, Math.round(n));
            else if (st.round === "9") { const c = Math.max(1, Math.ceil(n)); n = c >= 10 ? c - (c % 10) + 9 : c; }
            else n = Math.round(n * 100) / 100;
            return n;
        };
        const renderForm = () => {
            const f = sh.querySelector("#b-form");
            if (st.kind === "state") {
                f.innerHTML = `<div class="field"><div class="segmented" id="b-state">
                    <button data-v="activate" class="${st.value === "activate" ? "active" : ""}">Включить все</button>
                    <button data-v="deactivate" class="${st.value === "deactivate" ? "active" : ""}">Выключить все</button></div></div>`;
                f.querySelectorAll("[data-v]").forEach((b) => b.addEventListener("click", () => { st.value = b.dataset.v; renderForm(); renderPreview(); }));
                return;
            }
            const label = st.kind === "percent" ? "Изменить на, %" : st.kind === "add" ? `Изменить на, ${cur}` : `Новая цена, ${cur}`;
            const hint = st.kind === "percent" ? "10 — поднять на 10%, −10 — снизить на 10%." : st.kind === "add" ? "50 — прибавить 50, −50 — убавить 50." : "Все выбранные лоты получат одну цену.";
            f.innerHTML = `<div class="field"><label for="b-val">${label}</label>
                <input type="number" inputmode="decimal" step="any" id="b-val" value="${esc(st.value)}" placeholder="${st.kind === "set" ? "Например, 199" : "Например, 10"}"><div class="hint">${hint}</div></div>
                <div class="field"><label>Округление</label><div class="segmented" id="b-round">
                    <button data-r="2" class="${st.round === "2" ? "active" : ""}">До копеек</button>
                    <button data-r="int" class="${st.round === "int" ? "active" : ""}">До целых</button>
                    <button data-r="9" class="${st.round === "9" ? "active" : ""}">…9</button></div></div>`;
            const vi = f.querySelector("#b-val");
            vi.addEventListener("input", () => { st.value = vi.value; renderPreview(); });
            f.querySelectorAll("[data-r]").forEach((b) => b.addEventListener("click", () => { st.round = b.dataset.r; renderForm(); renderPreview(); }));
        };
        const renderPreview = () => {
            const t = targets();
            const pv = sh.querySelector("#b-preview");
            sh.querySelector("#b-count").textContent = `${t.length} ${plural(t.length, "лот", "лота", "лотов")}`;
            const applyBtn = sh.querySelector("#b-apply");
            let ready = t.length > 0;
            const rows = t.slice(0, 6).map((l) => {
                let right;
                if (st.kind === "state") {
                    if (!st.value) ready = false;
                    right = st.value ? `<span class="badge ${st.value === "activate" ? "closed" : "muted"}">${st.value === "activate" ? "включится" : "выключится"}</span>` : "";
                } else {
                    const base = l.my_price;
                    const exact = st.kind === "set" || l.my_price_exact;
                    const v = parseFloat(String(st.value).replace(",", "."));
                    const n = st.kind === "set" ? calc(0) : (base != null ? calc(base) : null);
                    if (isNaN(v) || (n !== null && !(n > 0))) ready = false;
                    const old = base != null ? `<span class="tnum" style="color:var(--muted);text-decoration:line-through;font-size:13px">${num(base)}</span>` : "";
                    if (isNaN(v)) right = base != null ? `<span class="price tnum">${money(base, l.currency)}</span>` : `<span class="s" style="color:var(--muted)">цена уточняется…</span>`;
                    else if (n === null) right = `<span class="price tnum">${st.kind === "percent" ? `${v > 0 ? "+" : ""}${num(v)}%` : `${v > 0 ? "+" : ""}${money(v, l.currency)}`}</span>`;
                    else right = `${old}<span class="price tnum" style="color:${n > 0 ? "var(--text)" : "var(--red)"}">${exact ? "" : "≈ "}${money(n, l.currency)}</span>`;
                }
                return `<div class="item no-icon"><div class="body"><div class="t"><span class="txt">${esc(l.title)}</span></div><div class="s">${esc(l.game)}</div></div><div class="right">${right}</div></div>`;
            }).join("");
            pv.innerHTML = rows + (t.length > 6 ? `<div class="item no-icon"><div class="body s" style="color:var(--muted)">…и ещё ${t.length - 6}</div></div>` : "") ||
                `<div class="item no-icon"><div class="body s">Нет подходящих лотов</div></div>`;
            applyBtn.disabled = !ready;
            applyBtn.style.opacity = ready ? 1 : .5;
            applyBtn.querySelector("span").textContent = `Применить к ${t.length} ${plural(t.length, "лоту", "лотам", "лотам")}`;
        };

        sh.querySelectorAll("#b-kind [data-k]").forEach((b) => b.addEventListener("click", () => {
            st.kind = b.dataset.k; st.value = "";
            sh.querySelectorAll("#b-kind [data-k]").forEach((x) => x.classList.toggle("active", x === b));
            renderForm(); renderPreview(); haptic("light");
        }));
        sh.querySelector("#b-only").addEventListener("change", (e) => { st.onlyActive = e.target.checked; renderPreview(); });
        renderForm(); renderPreview();

        // Уточняем «вашу» цену: по одному лоту из каждого раздела (дальше сервер оценит остальные по коэффициенту комиссии)
        (async () => {
            const bySub = new Map();
            scope.lots.forEach((l) => { if (l.my_price == null && !bySub.has(l.subId)) bySub.set(l.subId, l.id); });
            const ids = [...bySub.values()].slice(0, 8);
            if (!ids.length) return;
            for (const id of ids) {
                if (!document.body.contains(sh)) return;
                try { await api(`/api/lots/${id}`); } catch (e) {}
            }
            try {
                const fresh = await api("/api/lots");
                const map = new Map(allLots(fresh.games).map((l) => [l.id, l]));
                scope.lots.forEach((l) => { const f = map.get(l.id); if (f) { l.my_price = f.my_price; l.my_price_exact = f.my_price_exact; } });
                if (document.body.contains(sh) && sh.querySelector("#b-preview")) renderPreview();
            } catch (e) {}
        })();

        sh.querySelector("#b-apply").addEventListener("click", async () => {
            const t = targets();
            const what = st.kind === "state" ? (st.value === "activate" ? "Включить" : "Выключить") + ` ${t.length} ${plural(t.length, "лот", "лота", "лотов")}?`
                : `Изменить цену у ${t.length} ${plural(t.length, "лота", "лотов", "лотов")}? Это займёт около ${Math.max(1, Math.round(t.length * 2.5 / 60))} мин.`;
            if (!(await confirmDialog(what))) return;
            const op = st.kind === "state" ? { kind: st.value } : { kind: st.kind, value: st.value, round: st.round };
            let job;
            try { job = (await api("/api/lots/bulk", { method: "POST", body: { ids: t.map((l) => l.id), op } })).job; }
            catch (e) { toast(e.message, "err"); notify("error"); return; }
            runBulkProgress(sh, job, scope, onDone);
        });
    }

    async function runBulkProgress(sh, jobId, scope, onDone) {
        const box = sh.querySelector("#bulk");
        const titleOf = (id) => (scope.lots.find((l) => l.id === id) || {}).title || `Лот ${id}`;
        box.innerHTML = `
            <div class="head"><div class="ic tint-brand" style="width:42px;height:42px;border-radius:13px;display:grid;place-items:center">${icon("refresh")}</div>
                <div style="flex:1"><div class="title" id="p-title">Применяю изменения…</div><div class="sub" id="p-sub">Не закрывайте Cardinal. Окно можно закрыть — работа продолжится.</div></div></div>
            <div class="share"><div class="top"><span id="p-cnt">0 из ?</span><b id="p-pct">0%</b></div><div class="track"><i id="p-bar" style="width:0%"></i></div></div>
            <div class="list" id="p-res" style="margin-top:14px"></div>
            <div style="margin-top:14px"><button class="btn secondary" id="p-close">Закрыть</button></div>`;
        box.querySelector("#p-close").addEventListener("click", () => closeSheet());
        while (true) {
            let j;
            try { j = await api(`/api/lots/jobs/${jobId}`); } catch (e) { await new Promise((r) => setTimeout(r, 2000)); continue; }
            const pct = Math.round(j.done / j.total * 100);
            const cnt = box.querySelector("#p-cnt");
            if (!cnt) return;  // окно закрыли
            cnt.textContent = `${j.done} из ${j.total}`;
            box.querySelector("#p-pct").textContent = `${pct}%`;
            box.querySelector("#p-bar").style.width = `${pct}%`;
            const failed = j.results.filter((r) => !r.ok);
            box.querySelector("#p-res").innerHTML = failed.map((r) =>
                `<div class="item no-icon"><div class="body"><div class="t"><span class="txt">${esc(titleOf(r.id))}</span></div><div class="s" style="color:var(--red)">${esc(r.error)}</div></div></div>`).join("");
            if (j.status === "finished") {
                box.querySelector("#p-title").textContent = j.failed ? `Готово, с ошибками: ${j.failed}` : "Готово";
                box.querySelector("#p-sub").textContent = `Успешно изменено: ${j.ok} из ${j.total}`;
                notify(j.failed ? "warning" : "success");
                onDone && onDone();
                return;
            }
            await new Promise((r) => setTimeout(r, 1200));
        }
    }

    // ---------- Чёрный список ----------
    function confirmDialog(text) {
        return new Promise((resolve) => {
            if (inTelegram && tg.showConfirm && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) tg.showConfirm(text, (ok) => resolve(!!ok));
            else resolve(window.confirm(text));
        });
    }

    async function blacklistChange(action, nickname) {
        const r = await api(`/api/blacklist/${action}`, { method: "POST", body: { nickname } });
        notify("success");
        toast(action === "add" ? `${nickname} добавлен в чёрный список` : `${nickname} убран из чёрного списка`);
        return r.users;
    }

    async function renderBlacklist(_, alive) {
        paint(pageHead("Чёрный список") + sk(120) + sk(58 * 4));
        let d, s;
        try { [d, s] = await Promise.all([api("/api/blacklist"), api("/api/settings")]); }
        catch (e) { if (alive()) paint(pageHead("Чёрный список") + errorBox(e)); return; }
        if (!alive()) return;

        let users = d.users;
        let query = "";
        const rules = (s.groups.find((g) => g.items[0] && g.items[0].section === "BlockList") || { items: [] }).items;
        const activeRules = rules.filter((r) => r.value);

        const addBlock = `
            <div class="list">
                <div class="field">
                    <label for="bl-nick">Добавить покупателя</label>
                    <div style="display:flex;gap:8px">
                        <input type="text" id="bl-nick" placeholder="Ник на FunPay" autocomplete="off" autocapitalize="off" spellcheck="false" style="flex:1">
                        <button class="btn-sm primary" id="bl-add" style="padding:0 16px">Добавить</button>
                    </div>
                    <div class="hint">Ник пишется точно как на FunPay, с учётом регистра.</div>
                </div>
            </div>`;
        const rulesBlock = `
            ${sectionHead("Что происходит с ними")}
            <div class="list">
                ${activeRules.length ? activeRules.map((r) => `<div class="item"><div class="ic tint-red">${icon((SETTING_ICONS[r.option] || ["ban"])[0])}</div><div class="body"><div class="t">${esc(r.label)}</div></div></div>`).join("")
                    : `<div class="item"><div class="ic tint-amber">${icon("alert")}</div><div class="body"><div class="t">Ни одно ограничение не включено</div><div class="s">Список ни на что не влияет, пока не включите ограничения в Настройках</div></div></div>`}
                <button class="item clickable" id="bl-rules"><div class="ic tint-gray">${icon("sliders")}</div><div class="body"><div class="t">Изменить ограничения</div></div><div class="chev">${icon("chevron")}</div></button>
            </div>`;
        const head = pageHead("Чёрный список", "Ограничения для проблемных покупателей");
        paint(isDesktop()
            ? `${head}<div class="two-col"><div>${addBlock}${rulesBlock}</div><div><div id="bl-list"></div></div></div>`
            : `${head}${addBlock}${sectionHead("В списке")}<div id="bl-list"></div>${rulesBlock}`);

        const listEl = $("bl-list");
        const draw = () => {
            const q = query.trim().toLowerCase();
            const items = users.filter((u) => !q || u.toLowerCase().includes(q));
            const head = isDesktop() ? `<div class="section-head" style="margin-top:0"><h3>В списке · ${users.length}</h3></div>` : "";
            const search = users.length > 8 ? `<label class="search">${icon("search")}<input id="bl-q" type="search" placeholder="Найти в списке" value="${esc(query)}"></label>` : "";
            if (!users.length) {
                listEl.innerHTML = head + emptyBox("users", "Список пуст", "Добавьте ник выше или нажмите «В чёрный список» в карточке заказа");
                return;
            }
            listEl.innerHTML = head + search + (items.length ? `<div class="list">${items.map((u) => `
                <div class="item">
                    ${buyerAvatar(u)}
                    <div class="body"><div class="t"><span class="txt">${esc(u)}</span></div></div>
                    <button class="btn-sm" data-unban="${esc(u)}">Убрать</button>
                </div>`).join("")}</div>` : emptyBox("search", "Не найдено", "Попробуйте другой ник"));
            const qi = $("bl-q");
            if (qi) qi.addEventListener("input", (e) => { query = e.target.value; const pos = e.target.selectionStart; draw(); const n = $("bl-q"); n.focus(); n.setSelectionRange(pos, pos); });
            listEl.querySelectorAll("[data-unban]").forEach((b) => b.addEventListener("click", async () => {
                const nick = b.dataset.unban;
                if (!(await confirmDialog(`Убрать ${nick} из чёрного списка?`))) return;
                b.disabled = true;
                try { users = await blacklistChange("remove", nick); draw(); }
                catch (e) { toast(e.message, "err"); b.disabled = false; }
            }));
        };
        draw();

        const add = async () => {
            const inp = $("bl-nick");
            const nick = inp.value.trim();
            if (!nick) { inp.focus(); return; }
            $("bl-add").disabled = true;
            try { users = await blacklistChange("add", nick); inp.value = ""; draw(); }
            catch (e) { toast(e.message, "err"); notify("error"); }
            finally { $("bl-add").disabled = false; }
        };
        $("bl-add").addEventListener("click", add);
        $("bl-nick").addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
        $("bl-rules").addEventListener("click", () => { haptic(); back(); });
    }

    // ---------- вход из браузера ----------
    function showLogin() {
        booted = false;
        $("sidebar").innerHTML = ""; $("topbar").innerHTML = ""; $("tabbar").innerHTML = "";
        root.dataset.layout = "mobile";
        paint(`
            <div class="login"><div class="box">
                <div class="logo">${LOGO}</div>
                <h1>Cardinal<span style="color:var(--brand)">+</span></h1>
                <p>Панель управления FunPay Cardinal. Войдите через Telegram-бота — пароль не нужен.</p>
                <div class="list steps">
                    <div class="item"><div class="step-n">1</div><div class="body"><div class="t">Откройте своего бота Cardinal</div></div></div>
                    <div class="item"><div class="step-n">2</div><div class="body"><div class="t">Отправьте команду <code>/web</code></div></div></div>
                    <div class="item"><div class="step-n">3</div><div class="body"><div class="t">Нажмите «Открыть в браузере»</div><div class="s">Ссылка одноразовая и действует 5 минут</div></div></div>
                </div>
            </div></div>`);
    }

    // ---------- старт ----------
    async function boot() {
        if (!inTelegram && !initData()) {
            try { await api("/api/me"); }
            catch (e) { showLogin(); return; }
        }
        root.dataset.layout = layoutFor(getMode());
        booted = true;
        buildShell();
        render();
        loadChats().catch(() => {});
    }
    boot();
})();
