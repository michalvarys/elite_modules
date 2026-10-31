/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { MoveConfirmDialog, shortDayLabel } from "@elite_vet_reservation/move_dialog/move_dialog";
import { setSoundOn, playChime, isSoundOn } from "@elite_vet_reservation/sound/sound";
import { Component, useRef, useState, onWillStart, onWillUnmount } from "@odoo/owl";

const PX_PER_MIN = 1.6;   // 15 min = 24 px
const BAND_W = 16;        // width of the doctor shift band on the left of a column
const BAND_GAP = 2;

function pad(n) { return String(n).padStart(2, "0"); }
function hhmm(min) { return pad(Math.floor(min / 60)) + ":" + pad(min % 60); }
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
// Noon, so shifting by days never skips a day across a DST change.
function parseIso(iso) { return new Date(iso + "T12:00:00"); }
function nowMinute() { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
// Czech names hardcoded: must not depend on the browser or user language.
const WEEKDAY_NAMES = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"];
const WEEKDAY_ABBR = ["po", "út", "st", "čt", "pá", "so", "ne"];
function weekdayIndex(d) { return (d.getDay() + 6) % 7; }   // 0 = Monday

// White text would be unreadable on a light color (a doctor may pick e.g. yellow).
function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return "#fff";
    const n = parseInt(m[1], 16);
    const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.62 ? "#1e293b" : "#fff";
}

// Width of the "Waiting from web" panel: drag handle between panel and board, remembered by the browser.
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

// Task 24: Vše | Web | Klinika on the board, remembered by the browser.
// WinVet entries are shown in "Vše" only; blocks always (they are not bookings).
const SOURCE_FILTER_KEY = "elite_vet_reservation.board_source_filter";
export const SOURCE_FILTERS = [
    { key: "all", label: "Vše", title: "Všechny rezervace i záznamy z WinVetu" },
    { key: "web", label: "Web", title: "Jen rezervace z webu" },
    { key: "clinic", label: "Klinika", title: "Jen rezervace založené na klinice (bez záznamů z WinVetu)" },
];

function loadSourceFilter() {
    try {
        const v = localStorage.getItem(SOURCE_FILTER_KEY);
        return SOURCE_FILTERS.some((f) => f.key === v) ? v : "all";
    } catch {
        return "all";
    }
}

export class ReservationBoard extends Component {
    static template = "elite_vet_reservation.Board";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            date: isoDate(new Date()), today: isoDate(new Date()), now: nowMinute(),
            data: null, loading: true, drag: null, busy: false,
            preview: null,   // hover preview of a waiting request (see hoverWaiting)
            soundOn: isSoundOn(),
            panelWidth: loadPanelWidth(),
            sourceFilter: loadSourceFilter(),
        });
        this.gridRef = useRef("grid");
        onWillStart(() => this.load());
        // Live updates: after every reservation / schedule change the server notifies the Reception
        // group (see models/live.py) and the board silently reloads right away.
        this.busService = useService("bus_service");
        this.onBusChange = (payload) => this.onLiveChange(payload);
        this.busService.subscribe("elite_vet_reservation/changed", this.onBusChange);
        this.busService.start();
        // Polling is only a fallback (dropped websocket); the bus delivers new requests immediately.
        // A failed reload (expired session, server down) must not raise an unhandled rejection.
        this.timer = setInterval(() => this.load(true).catch(() => {}), 60000);
        onWillUnmount(() => {
            clearInterval(this.timer);
            clearTimeout(this.hoverTimer);
            this.busService.unsubscribe("elite_vet_reservation/changed", this.onBusChange);
        });
    }

    onLiveChange() {
        // The "new web request" notification and sound are handled by the ../sound service (Odoo-wide).
        this.load(true).catch(() => {});
    }

    // ---------- data ----------
    async load(silent = false) {
        if (!silent) this.state.loading = true;
        const date = this.state.date;
        const data = await this.orm.call("elite.vet.reservation", "board_data", [date]);
        // The day may have changed meanwhile; a stale response would overwrite the board with another day.
        if (date !== this.state.date) return;
        // The "now" line and today highlight move with every reload (also across midnight).
        this.state.today = isoDate(new Date());
        this.state.now = nowMinute();
        this.state.data = data;
        // A confirmed / rejected request leaves the panel before mouseleave fires – otherwise
        // the preview would stay stuck on the board.
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

    // ---------- header ----------
    get dayTitle() {
        const d = parseIso(this.state.date);
        return WEEKDAY_NAMES[weekdayIndex(d)] + " " + d.getDate() + ". " + (d.getMonth() + 1) + ". " + d.getFullYear();
    }
    get weekDays() {
        const monday = parseIso(this.state.date);
        monday.setDate(monday.getDate() - weekdayIndex(monday));
        const out = [];
        for (let i = 0; i < 7; i++) {
            const d = new Date(monday);
            d.setDate(monday.getDate() + i);
            const iso = isoDate(d);
            const today = iso === this.state.today;
            // Holidays of the loaded week (board_data.week_holidays); none while loading another week.
            const holiday = (this.state.data && this.state.data.week_holidays || {})[iso] || "";
            out.push({
                iso, short: WEEKDAY_ABBR[i], label: d.getDate() + ". " + (d.getMonth() + 1) + ".",
                selected: iso === this.state.date, today, holiday,
                title: [today ? "Dnes" : "", holiday ? "Státní svátek: " + holiday : ""].filter(Boolean).join(" · "),
            });
        }
        return out;
    }

    // ---------- "now" line ----------
    get showNow() {
        return this.state.date === this.state.today && this.state.now >= this.axis.from && this.state.now <= this.axis.to;
    }

    // ---------- events ----------
    eventLabel(e) {
        if (e.kind === "block") return e.name;
        // WinVet calendar entry (elite_vet_winvet): pet (owner) from the card index, else the WinVet text.
        if (e.pet && e.owner) return e.pet + " (" + e.owner + ")";
        return e.pet || e.owner || e.name;
    }
    eventTitle(e) {
        if (e.kind === "block") return e.time_label + "\n" + e.name;
        if (this.isWinvet(e)) return this.winvetTitle(e);
        const lines = [e.time_label + " · " + this.eventLabel(e)];
        if (e.procedure) lines.push("Úkon: " + e.procedure);
        if (e.doctor) lines.push("Lékařka: " + e.doctor);
        if (e.linked) lines.push("Společný zákrok, také v: " + e.linked);
        if (e.kind === "reservation") lines.push(this.originTitle(e));
        if (e.phone) lines.push("Telefon: " + e.phone);
        if (e.email) lines.push("E-mail: " + e.email);
        if (e.problem) lines.push("Popis problému: " + e.problem);
        return lines.join("\n");
    }
    isShort(e) { return e.end - e.start <= 15; }
    // ---------- source: web / clinic (task 24) ----------
    get sourceFilters() { return SOURCE_FILTERS; }
    isWeb(e) { return e.kind === "reservation" && e.source === "web"; }
    originTitle(e) {
        if (this.isWeb(e)) return "Z webu – objednal(a) se klient sám" + (e.created_at ? ", " + e.created_at : "");
        if (e.created_by) return "Založil(a): " + e.created_by + (e.created_at ? ", " + e.created_at : "");
        return "Založeno na klinice" + (e.created_at ? ", " + e.created_at : "");
    }
    passesSourceFilter(e) {
        const f = this.state.sourceFilter;
        if (f === "all" || e.kind === "block") return true;
        if (this.isWinvet(e)) return false;
        return f === "web" ? this.isWeb(e) : !this.isWeb(e);
    }
    get hiddenCount() {
        if (!this.state.data) return 0;
        return this.state.data.events.filter((e) => !this.passesSourceFilter(e)).length;
    }
    setSourceFilter(key) {
        this.state.sourceFilter = key;
        try {
            localStorage.setItem(SOURCE_FILTER_KEY, key);
        } catch {
            // without storage the choice lasts until a page reload
        }
    }
    // ---------- WinVet calendar (read-only entries, elite_vet_winvet) ----------
    isWinvet(e) { return e.kind === "winvet"; }
    winvetTitle(e) {
        const lines = ["Z WinVetu · " + e.time_label, this.eventLabel(e)];
        if (e.procedure) lines.push("Činnost: " + e.procedure);
        if (e.winvet_title && e.winvet_title !== this.eventLabel(e)) lines.push("Ve WinVetu: " + e.winvet_title);
        lines.push("Jen pro čtení – mění se ve WinVetu. Termín je obsazený.");
        return lines.join("\n");
    }
    winvetNoteTitle(n) {
        return "Z WinVetu, celý den: " + n.label + (n.activity ? "\nČinnost: " + n.activity : "") +
            "\nJen poznámka – termíny neblokuje.";
    }

    // ---------- geometry ----------
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
    otherEventsFor(room) { return this.eventsFor(room).filter((e) => !this.isWebBlock(e) && this.passesSourceFilter(e)); }
    webBlockTitle(b) { return b.time_label + "\n" + b.name + "\nJen web – recepce sem objednat smí (klik do sloupce)."; }

    // ---------- doctor shifts (bands on the left) ----------
    // Concurrent shifts sit side by side (lanes); events start after the bands.
    bandStyle(d) {
        return "top:" + this.top(d.from) + "px;height:" + this.height(d.from, d.to) + "px;left:" +
            (BAND_GAP + d.lane * (BAND_W + BAND_GAP)) + "px;width:" + BAND_W + "px;background:" + d.color;
    }
    bandTitle(d) { return d.name + " " + d.time_label + (d.from_roster ? " · z rozpisu služeb" : ""); }
    eventLeft(room) { return 4 + (room.lanes || 0) * (BAND_W + BAND_GAP); }
    eventStyle(room, e) {
        let style = "top:" + this.top(e.start) + "px;height:" + this.height(e.start, e.end) + "px";
        if (this.isWinvet(e)) {
            // plain light grey card with the WinVet colour as the left stripe (styles in board.scss)
            return style + ";left:" + this.eventLeft(room) + "px;border-left:7px solid " + (e.winvet_color || "#94a3b8");
        }
        if (e.kind !== "block") {
            style += ";left:" + this.eventLeft(room) + "px;background:" + e.color_hex + ";color:" + textOn(e.color_hex);
            // Left stripe in the color of the doctor the client is booked with.
            // A white line separates it even when the procedure color is similar to the doctor's.
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
        // Click in a cell = its start (floor); drag = nearest time (round).
        const snapped = (floor ? Math.floor(raw / step) : Math.round(raw / step)) * step;
        return Math.max(this.axis.from, snapped);
    }

    // ---------- interaction ----------
    openForm(resId, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "elite.vet.reservation", res_id: resId || false,
            views: [[false, "form"]], target: "new", context,
        }, { onClose: () => this.load(true) });
    }
    // A new reservation goes through the wizard (procedure → free time → client → summary), not an empty form.
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
    // ---------- blocks: Správce rezervací only (can_edit_blocks) ----------
    // Without the right blocks cannot be dragged and open read-only; clicks into the column
    // (also through web-only blocks) still book as before.
    get canEditBlocks() { return Boolean(this.state.data && this.state.data.can_edit_blocks); }
    isDraggable(e) { return !this.isWinvet(e) && (e.kind !== "block" || this.canEditBlocks); }
    openEvent(e) {
        if (this.isWinvet(e)) {
            // read-only form of the WinVet entry (no actions)
            this.action.doAction({
                type: "ir.actions.act_window", res_model: "elite.vet.winvet.calendar.event",
                res_id: e.winvet_event_id, views: [[false, "form"]], target: "new",
            });
            return;
        }
        if (e.kind === "block" && !this.canEditBlocks) {
            this.openForm(e.id, { form_view_ref: "elite_vet_reservation.view_reservation_block_readonly_form" });
        } else {
            this.openForm(e.id);
        }
    }
    // ---------- doctor shifts: edited in Rozpis služeb (roster) right from the board ----------
    openShiftForm(resModel, resId, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window", name: resId ? "Služba" : "Nová služba",
            res_model: resModel, res_id: resId || false,
            views: [[false, "form"]], target: "new", context,
        }, { onClose: () => this.load(true) });
    }
    // A roster shift opens the shift (its change goes to the website too); a manual service its own form.
    editShift(d) {
        if (!this.state.data.can_edit_shifts) return;
        if (d.shift_id) this.openShiftForm("elite.vet.shift", d.shift_id, { ev_keep_room: true });
        else this.openShiftForm("elite.vet.doctor.assignment", d.id);
    }
    // Without the right the band is no obstacle: the click books in the column as before.
    onBandClick(ev, d) {
        if (!this.state.data.can_edit_shifts) return;
        ev.stopPropagation();
        this.editShift(d);
    }
    addShift(room) {
        this.openShiftForm("elite.vet.shift", false,
            { default_date: this.state.date, default_room_id: room.id, ev_keep_room: true });
    }
    onColumnClick(ev, room) {
        // "Web only" blocks let clicks through (pointer-events: none): reception may book there.
        if (ev.target.closest(".evb-event")) return;
        this.newAt(room, this.minuteFromDrop(ev, ev.currentTarget, true));
    }
    onDragStart(ev, item, kind) {
        if (kind === "event" && !this.isDraggable(item)) {
            ev.preventDefault();
            return;
        }
        this.state.drag = { id: item.id, kind };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(item.id));
    }
    onDragEnd() { this.state.drag = null; }   // a cancelled drag (Esc) must not complete a later unrelated drop
    onDragOver(ev) { ev.preventDefault(); }
    async onDrop(ev, room) {
        ev.preventDefault();
        const drag = this.state.drag;
        if (!drag) return;
        this.state.drag = null;
        const min = this.minuteFromDrop(ev, ev.currentTarget);
        if (drag.kind === "waiting") {
            // Task 19: confirming a web request (and the e-mail to the client) also asks first.
            const w = this.state.data.waiting.find((x) => x.id === drag.id);
            if (!w) return;
            this.askConfirmRequest(w, this.state.date, min, room.id, null);
            return;
        }
        // Request 25. 10.: a move happens only after the user confirms it (an accidental drop
        // changes nothing); dropped back on the same place = nothing to do.
        const event = this.state.data.events.find((e) => e.id === drag.id);
        if (!event) return;
        if (event.start === min && (event.room_id || false) === room.id) return;
        this.askMove(event, min, room);
    }
    get roomChoices() {
        return (this.state.data?.rooms || []).map((r) => ({ id: r.id, name: r.name }));
    }
    /** Task 25: "Přesunout Rex (Novák) z čt 29. 10. 9:00–9:20, Ordinace 1 na …?" with the date,
     *  time and room still editable; the server message stays in the dialog. */
    askMove(event, min, room) {
        const day = this.state.date;
        const oldRoom = event.room_id
            ? (this.state.data.rooms.find((r) => r.id === event.room_id)?.name || "")
            : "všechny ordinace";
        const who = event.kind === "block"
            ? "blokaci „" + event.name + "“"
            : ([event.pet, event.owner ? "(" + event.owner + ")" : ""].filter(Boolean).join(" ") || event.name);
        this.dialog.add(MoveConfirmDialog, {
            title: "Přesunout?",
            confirmLabel: "Přesunout",
            verb: "Přesunout",
            who,
            from: shortDayLabel(day) + " " + event.time_label + ", " + oldRoom,
            date: day,
            minute: min,
            roomId: room.id,
            rooms: this.roomChoices,
            duration: event.end - event.start,
            step: this.state.data.step,
            mailTo: event.mail_on_move || false,
            mailOnTimeChange: true,
            origDate: day,
            origMinute: event.start,
            origRoomId: event.room_id || false,
            mailText: "Klient dostane e-mail o změně termínu (" + (event.mail_on_move || "") + ").",
            mailLabel: "Poslat klientovi e-mail o změně",
            onConfirm: async ({ date, minute, endMinute, roomId, notify, force }) => {
                await this.orm.call("elite.vet.reservation", "board_move",
                    [event.id, date, minute, roomId, notify, endMinute, force]);
                await this.afterChange(date);
            },
        });
    }
    /** Task 19 + 25: "Potvrdit žádost Rex (Novák) na čt 29. 10. 10:00–10:20, Ordinace 2?" with the
     *  date, time and room editable (+ the confirmation e-mail checkbox when it has an e-mail).
     *  `doctorId` (a suggestion) is kept only while its room stays chosen. */
    askConfirmRequest(w, dateIso, min, roomId, doctorId) {
        this.dialog.add(MoveConfirmDialog, {
            title: "Potvrdit žádost?",
            confirmLabel: "Potvrdit",
            verb: "Potvrdit žádost",
            who: [w.pet, w.owner ? "(" + w.owner + ")" : ""].filter(Boolean).join(" ") || w.name,
            date: dateIso,
            minute: min,
            roomId,
            rooms: this.roomChoices,
            duration: w.duration || 0,
            step: this.state.data.step,
            mailTo: w.email || false,
            mailText: "Klient dostane potvrzovací e-mail (" + (w.email || "") + ").",
            mailLabel: "Poslat klientovi potvrzení",
            onConfirm: async ({ date, minute, endMinute, roomId: chosen, notify, force }) => {
                const doctor = doctorId && chosen === roomId ? doctorId : null;
                await this.orm.call("elite.vet.reservation", "board_confirm",
                    [w.id, date, minute, chosen, doctor, notify, endMinute, force]);
                const room = this.roomChoices.find((r) => r.id === chosen)?.name || "";
                this.notification.add("Potvrzeno: " + shortDayLabel(date) + " · " + room, { type: "success" });
                await this.afterChange(date);
            },
        });
    }
    /** After a move / confirmation to another day the board follows it. */
    async afterChange(date) {
        if (date !== this.state.date) {
            this.goTo(date);
        } else {
            await this.load(true);
        }
    }
    confirmSuggestion(w, sug) {
        if (this.state.busy) return;
        this.leaveWaiting();
        this.askConfirmRequest(w, w.date, w.minute, sug.room_id, sug.doctor_id || null);
    }
    // The new-request sound is played by the ../sound service (Odoo-wide); this is just the toggle.
    toggleSound() {
        this.state.soundOn = !this.state.soundOn;
        setSoundOn(this.state.soundOn);
        if (this.state.soundOn) playChime();   // preview of how it sounds
    }

    // ---------- waiting panel width ----------
    clampPanelWidth(w) {
        // Leave the board at least 400 px so the panel cannot cover the whole screen.
        const max = Math.max(PANEL_MIN, Math.min(PANEL_MAX, window.innerWidth - 400));
        return Math.round(Math.min(max, Math.max(PANEL_MIN, w)));
    }
    get panelStyle() { return "width:" + this.clampPanelWidth(this.state.panelWidth) + "px"; }
    savePanelWidth() {
        try {
            localStorage.setItem(PANEL_KEY, String(this.state.panelWidth));
        } catch {
            // without storage the width lasts only until a page reload
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
        const step = ev.shiftKey ? 60 : 20;
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
            ev.preventDefault();
            const w = this.clampPanelWidth(this.state.panelWidth);
            this.state.panelWidth = this.clampPanelWidth(w + (ev.key === "ArrowRight" ? step : -step));
            this.savePanelWidth();
        }
    }
    resetPanelWidth() {
        this.state.panelWidth = PANEL_DEFAULT;
        this.savePanelWidth();
    }

    // ---------- waiting request preview ----------
    // Hovering a request switches the board to its day (and stays there), scrolls to its time
    // and draws a dashed preview in the suggested rooms. A short delay keeps the board from
    // jumping while the mouse just passes over the panel.
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
        // The column header is sticky (100 px); time 0 is right below it.
        const head = 100, y1 = this.top(from), y2 = this.top(to);
        const visibleTop = grid.scrollTop, visibleBottom = grid.scrollTop + grid.clientHeight - head;
        if (y1 < visibleTop || y2 > visibleBottom) {
            grid.scrollTo({ top: Math.max(0, y1 - 60), behavior: "smooth" });
        }
    }
    previewFor(room) {
        const p = this.state.preview;
        if (!p || !this.state.data || this.state.data.date !== p.date) return null;
        // Free: preview in the suggested rooms. Busy: red across all rooms, to show what is there.
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
