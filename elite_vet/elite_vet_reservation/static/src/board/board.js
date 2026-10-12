/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { setSoundOn, playChime, isSoundOn } from "@elite_vet_reservation/sound/sound";
import { Component, useRef, useState, onWillStart, onWillUnmount } from "@odoo/owl";

const PX_PER_MIN = 1.6;   // 15 min = 24 px
const BAND_W = 16;        // šířka pruhu služby lékařky vlevo ve sloupci
const BAND_GAP = 2;

function pad(n) { return String(n).padStart(2, "0"); }
function hhmm(min) { return pad(Math.floor(min / 60)) + ":" + pad(min % 60); }
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
// Poledne, aby posun o dny nepreskocil kvuli zmene letniho casu.
function parseIso(iso) { return new Date(iso + "T12:00:00"); }
function nowMinute() { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
// Ceske nazvy natvrdo: nesmi zalezet na jazyce prohlizece ani uzivatele.
const DNY = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"];
const WEEKDAY_ABBR = ["po", "út", "st", "čt", "pá", "so", "ne"];
function weekdayIndex(d) { return (d.getDay() + 6) % 7; }   // 0 = pondělí

// Na světlé barvě (lékařka si může vybrat třeba žlutou) by bílý text nebyl čitelný.
function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return "#fff";
    const n = parseInt(m[1], 16);
    const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.62 ? "#1e293b" : "#fff";
}

// Šířka panelu „Čekající z webu“: táhlo mezi panelem a tabulí, pamatuje si ji prohlížeč.
const PANEL_KEY = "elite_vet_reservation.panel_width";
const PANEL_DEFAULT = 280, PANEL_MIN = 200, PANEL_MAX = 720;

function loadPanelWidth() {
    try {
        const w = parseInt(localStorage.getItem(PANEL_KEY), 10);
        return Number.isFinite(w) ? w : PANEL_DEFAULT;
    } catch {
        return PANEL_DEFAULT;
    }
}

export class ReservationBoard extends Component {
    static template = "elite_vet_reservation.Board";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            date: isoDate(new Date()), today: isoDate(new Date()), now: nowMinute(),
            data: null, loading: true, drag: null, busy: false,
            preview: null,   // náhled čekající žádosti při najetí myší (viz hoverWaiting)
            zvuk: isSoundOn(),
            panelWidth: loadPanelWidth(),
        });
        this.gridRef = useRef("grid");
        onWillStart(() => this.load());
        // Živá aktualizace: server po každé změně rezervací / rozpisu pošle zprávu skupině Recepce
        // (viz models/live.py) a tabule se hned tiše obnoví.
        this.busService = useService("bus_service");
        this.onBusChange = (payload) => this.onLiveChange(payload);
        this.busService.subscribe("elite_vet_reservation/changed", this.onBusChange);
        this.busService.start();
        // Polling jen jako záloha (spadlé spojení websocketu); nové žádosti nese bus hned.
        // Neuspesna obnova (vyprsela session, server nedostupny) nesmi hodit neosetreny reject.
        this.timer = setInterval(() => this.load(true).catch(() => {}), 60000);
        onWillUnmount(() => {
            clearInterval(this.timer);
            clearTimeout(this.hoverTimer);
            this.busService.unsubscribe("elite_vet_reservation/changed", this.onBusChange);
        });
    }

    onLiveChange() {
        // Zprávu „Nová žádost z webu“ a zvuk má na starosti služba ../zvuk (v celém Odoo).
        this.load(true).catch(() => {});
    }

    // ---------- data ----------
    async load(silent = false) {
        if (!silent) this.state.loading = true;
        const date = this.state.date;
        const data = await this.orm.call("elite.vet.reservation", "board_data", [date]);
        // Mezitim se mohl prepnout den; starsi odpoved by prepsala tabuli daty jineho dne.
        if (date !== this.state.date) return;
        // Cara „teď“ a zvyrazneni dneska se posouvaji s kazdou obnovou (i pres pulnoc).
        this.state.today = isoDate(new Date());
        this.state.now = nowMinute();
        this.state.data = data;
        // Potvrzená / odmítnutá žádost zmizí z panelu dřív, než přijde mouseleave – náhled
        // by jinak zůstal viset v kalendáři.
        const p = this.state.preview;
        if (p && !data.waiting.some((w) => w.id === p.id)) this.state.preview = null;
        this.state.loading = false;
    }
    shiftDay(delta) {
        const d = parseIso(this.state.date);
        d.setDate(d.getDate() + delta);
        this.goTo(isoDate(d));
    }
    goTo(iso) { this.state.date = iso; this.load(); }
    today() { this.goTo(isoDate(new Date())); }
    onDateInput(ev) { if (ev.target.value) { this.goTo(ev.target.value); } }

    // ---------- hlavicka ----------
    get dayTitle() {
        const d = parseIso(this.state.date);
        return DNY[weekdayIndex(d)] + " " + d.getDate() + ". " + (d.getMonth() + 1) + ". " + d.getFullYear();
    }
    get weekDays() {
        const monday = parseIso(this.state.date);
        monday.setDate(monday.getDate() - weekdayIndex(monday));
        const out = [];
        for (let i = 0; i < 7; i++) {
            const d = new Date(monday);
            d.setDate(monday.getDate() + i);
            const iso = isoDate(d);
            out.push({
                iso, short: WEEKDAY_ABBR[i], label: d.getDate() + ". " + (d.getMonth() + 1) + ".",
                selected: iso === this.state.date, today: iso === this.state.today,
            });
        }
        return out;
    }

    // ---------- cara „teď“ ----------
    get showNow() {
        return this.state.date === this.state.today && this.state.now >= this.axis.from && this.state.now <= this.axis.to;
    }

    // ---------- udalosti ----------
    eventLabel(e) {
        if (e.kind === "block") return e.name;
        if (e.pet && e.owner) return e.pet + " (" + e.owner + ")";
        return e.pet || e.owner || e.name;
    }
    eventTitle(e) {
        if (e.kind === "block") return e.time_label + "\n" + e.name;
        const lines = [e.time_label + " · " + this.eventLabel(e)];
        if (e.procedure) lines.push("Úkon: " + e.procedure);
        if (e.doctor) lines.push("Lékařka: " + e.doctor);
        if (e.spojena) lines.push("Společný zákrok, také v: " + e.spojena);
        if (e.phone) lines.push("Telefon: " + e.phone);
        if (e.email) lines.push("E-mail: " + e.email);
        if (e.problem) lines.push("Popis problému: " + e.problem);
        return lines.join("\n");
    }
    isShort(e) { return e.end - e.start <= 15; }

    // ---------- geometrie ----------
    get axis() { return this.state.data.axis; }
    get rows() {
        const out = [];
        for (let m = this.axis.from; m < this.axis.to; m += this.state.data.step) out.push(m);
        return out;
    }
    top(min) { return (min - this.axis.from) * PX_PER_MIN; }
    height(a, b) { return Math.max(12, (b - a) * PX_PER_MIN); }
    hhmm(m) { return hhmm(m); }
    isOpen(room, min) { return room.open.some(([f, t]) => f <= min && min < t); }
    eventsFor(room) { return this.state.data.events.filter((e) => e.room_id === room.id); }
    isWebBlock(e) { return e.kind === "block" && e.block_scope === "web"; }
    webBlocksFor(room) { return this.eventsFor(room).filter((e) => this.isWebBlock(e)); }
    otherEventsFor(room) { return this.eventsFor(room).filter((e) => !this.isWebBlock(e)); }
    webBlockTitle(b) { return b.time_label + "\n" + b.name + "\nJen web – recepce sem objednat smí (klik do sloupce)."; }

    // ---------- služby lékařek (pruhy vlevo) ----------
    // Souběžné služby jsou vedle sebe (lane), události začínají až za pruhy.
    bandStyle(d) {
        return "top:" + this.top(d.from) + "px;height:" + this.height(d.from, d.to) + "px;left:" +
            (BAND_GAP + d.lane * (BAND_W + BAND_GAP)) + "px;width:" + BAND_W + "px;background:" + d.color;
    }
    bandTitle(d) { return d.name + " " + d.time_label; }
    eventLeft(room) { return 4 + (room.lanes || 0) * (BAND_W + BAND_GAP); }
    eventStyle(room, e) {
        let style = "top:" + this.top(e.start) + "px;height:" + this.height(e.start, e.end) + "px";
        if (e.kind !== "block") {
            style += ";left:" + this.eventLeft(room) + "px;background:" + e.color_hex + ";color:" + textOn(e.color_hex);
            // Proužek vlevo v barvě lékařky, ke které je klient objednaný.
            // Bílá linka ho oddělí i tam, kde má úkon podobnou barvu jako lékařka.
            if (e.doctor_color) style += ";border-left:7px solid " + e.doctor_color + ";box-shadow:inset 2px 0 0 #fff,0 1px 2px rgba(0,0,0,.15)";
        }
        return style;
    }
    get globalBlocks() { return this.state.data.events.filter((e) => !e.room_id && e.kind === 'block'); }
    minuteFromDrop(ev, column, floor = false) {
        const rect = column.getBoundingClientRect();
        const y = ev.clientY - rect.top + column.scrollTop;
        const raw = this.axis.from + y / PX_PER_MIN;
        const step = this.state.data.step;
        // Klik do bunky = jeji zacatek (floor); pretazeni = nejblizsi cas (round).
        const snapped = (floor ? Math.floor(raw / step) : Math.round(raw / step)) * step;
        return Math.max(this.axis.from, snapped);
    }

    // ---------- interakce ----------
    openForm(resId, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "elite.vet.reservation", res_id: resId || false,
            views: [[false, "form"]], target: "new", context,
        }, { onClose: () => this.load(true) });
    }
    // Nová rezervace jde přes průvodce (úkon → volný čas → klient → shrnutí), ne přes prázdný formulář.
    openWizard(context = {}) {
        this.action.doAction("elite_vet_reservation.action_reservation_wizard", {
            additionalContext: { default_date: this.state.date, ...context },
            onClose: () => this.load(true),
        });
    }
    newAt(room, min) {
        this.openWizard({ default_minute: min, default_room_id: room.id });
    }
    newBlock() { this.openForm(false, { default_kind: "block", default_state: "confirmed" }); }
    onColumnClick(ev, room) {
        // Blokace „jen web“ kliky propouští (pointer-events: none): recepce tam smí objednat.
        if (ev.target.closest(".evb-event")) return;
        this.newAt(room, this.minuteFromDrop(ev, ev.currentTarget, true));
    }
    onDragStart(ev, item, kind) {
        this.state.drag = { id: item.id, kind };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(item.id));
    }
    onDragEnd() { this.state.drag = null; }   // zruseny tah (Esc) nesmi dokoncit pozdejsi cizi drop
    onDragOver(ev) { ev.preventDefault(); }
    async onDrop(ev, room) {
        ev.preventDefault();
        const drag = this.state.drag;
        if (!drag) return;
        const min = this.minuteFromDrop(ev, ev.currentTarget);
        try {
            if (drag.kind === "waiting") {
                await this.orm.call("elite.vet.reservation", "board_confirm", [drag.id, this.state.date, min, room.id]);
            } else {
                await this.orm.call("elite.vet.reservation", "board_move", [drag.id, this.state.date, min, room.id]);
            }
        } catch (e) {
            // Obsazeny termin vraci server jako chybu; karta zustane na puvodnim miste.
            this.notification.add(e.data?.message || e.message, { type: "danger" });
        }
        this.state.drag = null;
        await this.load(true);
    }
    async confirmSuggestion(w, sug) {
        if (this.state.busy) return;
        this.leaveWaiting();
        this.state.busy = true;
        try {
            await this.orm.call("elite.vet.reservation", "board_confirm",
                [w.id, w.date, w.minute, sug.room_id, sug.doctor_id || null]);
            this.notification.add("Potvrzeno: " + w.date_label + " · " + sug.room, { type: "success" });
        } catch (e) {
            this.notification.add(e.data?.message || e.message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
        await this.load(true);
    }
    // Zvuk nové žádosti hraje služba ../zvuk (v celém Odoo); tady jen vypínač.
    toggleSound() {
        this.state.zvuk = !this.state.zvuk;
        setSoundOn(this.state.zvuk);
        if (this.state.zvuk) playChime();   // ukázka, jak zní
    }

    // ---------- šířka panelu čekajících ----------
    clampPanelWidth(w) {
        // Tabuli nechat aspoň 400 px, ať se panel nedá roztáhnout přes celou obrazovku.
        const max = Math.max(PANEL_MIN, Math.min(PANEL_MAX, window.innerWidth - 400));
        return Math.round(Math.min(max, Math.max(PANEL_MIN, w)));
    }
    get panelStyle() { return "width:" + this.clampPanelWidth(this.state.panelWidth) + "px"; }
    savePanelWidth() {
        try {
            localStorage.setItem(PANEL_KEY, String(this.state.panelWidth));
        } catch {
            // bez úložiště platí šířka jen do obnovení stránky
        }
    }
    onResizeStart(ev) {
        ev.preventDefault();
        const handle = ev.currentTarget;
        handle.setPointerCapture(ev.pointerId);
        const startX = ev.clientX, startW = this.clampPanelWidth(this.state.panelWidth);
        document.body.classList.add("evb-resizing");
        const move = (e) => { this.state.panelWidth = this.clampPanelWidth(startW + e.clientX - startX); };
        const up = () => {
            handle.removeEventListener("pointermove", move);
            handle.removeEventListener("pointerup", up);
            handle.removeEventListener("pointercancel", up);
            document.body.classList.remove("evb-resizing");
            this.savePanelWidth();
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
        handle.addEventListener("pointercancel", up);
    }
    onResizeKey(ev) {
        const krok = ev.shiftKey ? 60 : 20;
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
            ev.preventDefault();
            const w = this.clampPanelWidth(this.state.panelWidth);
            this.state.panelWidth = this.clampPanelWidth(w + (ev.key === "ArrowRight" ? krok : -krok));
            this.savePanelWidth();
        }
    }
    resetPanelWidth() {
        this.state.panelWidth = PANEL_DEFAULT;
        this.savePanelWidth();
    }

    // ---------- náhled čekající žádosti ----------
    // Najetí myší na žádost přepne tabuli na její den (a tam zůstane), odroluje na čas
    // a do navržených ordinací nakreslí přerušovaný náhled. Krátká prodleva, ať tabule
    // neposkakuje, když myš jen přejíždí přes panel.
    hoverWaiting(w) {
        clearTimeout(this.hoverTimer);
        this.hoverTimer = setTimeout(() => this.showPreview(w), 200);
    }
    leaveWaiting() {
        clearTimeout(this.hoverTimer);
        this.state.preview = null;
    }
    hoverSuggestion(w, sug) {
        if (this.state.preview?.id === w.id) this.state.preview.focus = sug.room_id;
    }
    leaveSuggestion(w) {
        if (this.state.preview?.id === w.id) this.state.preview.focus = null;
    }
    async showPreview(w) {
        if (this.state.drag) return;
        this.state.preview = {
            id: w.id, date: w.date, minute: w.minute, end: w.minute + (w.duration || 15),
            name: w.name, time: w.time, free: w.suggestions.length > 0,
            rooms: w.suggestions.map((s) => s.room_id), focus: null,
        };
        if (w.date !== this.state.date) {
            this.state.date = w.date;
            await this.load(true);
        }
        this.scrollToMinute(w.minute, w.minute + (w.duration || 15));
    }
    scrollToMinute(from, to) {
        const grid = this.gridRef.el;
        if (!grid) return;
        // Hlavička sloupců je sticky (100 px), čas 0 je hned pod ní.
        const head = 100, y1 = this.top(from), y2 = this.top(to);
        const visibleTop = grid.scrollTop, visibleBottom = grid.scrollTop + grid.clientHeight - head;
        if (y1 < visibleTop || y2 > visibleBottom) {
            grid.scrollTo({ top: Math.max(0, y1 - 60), behavior: "smooth" });
        }
    }
    previewFor(room) {
        const p = this.state.preview;
        if (!p || !this.state.data || this.state.data.date !== p.date) return null;
        // Volno: náhled v navržených ordinacích. Obsazeno: červeně přes všechny, ať je vidět, co tam je.
        if (p.free && !p.rooms.includes(room.id)) return null;
        return p;
    }
    previewStyle(room, p) {
        return "top:" + this.top(p.minute) + "px;height:" + this.height(p.minute, p.end) + "px;left:" +
            this.eventLeft(room) + "px";
    }
    previewClass(room, p) {
        return {
            "evb-preview-busy": !p.free,
            "evb-preview-focus": p.focus === room.id,
            "evb-preview-dim": p.focus !== null && p.focus !== room.id,
        };
    }
    async reject(item) {
        this.leaveWaiting();
        if (!confirm("Odmítnout rezervaci " + item.name + "? Klientovi odejde e-mail o zrušení.")) return;
        await this.orm.call("elite.vet.reservation", "action_cancel", [[item.id], "clinic"]);
        await this.load(true);
    }
}

registry.category("actions").add("elite_vet_reservation.board", ReservationBoard);
