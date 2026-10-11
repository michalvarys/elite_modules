/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";

const PX_PER_MIN = 1.6;   // 15 min = 24 px

function pad(n) { return String(n).padStart(2, "0"); }
function hhmm(min) { return pad(Math.floor(min / 60)) + ":" + pad(min % 60); }
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
// Poledne, aby posun o dny nepreskocil kvuli zmene letniho casu.
function parseIso(iso) { return new Date(iso + "T12:00:00"); }
function nowMinute() { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
// Ceske nazvy natvrdo: nesmi zalezet na jazyce prohlizece ani uzivatele.
const DNY = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"];
const DNY_KRATCE = ["po", "út", "st", "čt", "pá", "so", "ne"];
function weekdayIndex(d) { return (d.getDay() + 6) % 7; }   // 0 = pondělí

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
        });
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
            this.busService.unsubscribe("elite_vet_reservation/changed", this.onBusChange);
        });
    }

    onLiveChange(payload) {
        if (payload?.new_web) {
            for (const label of payload.web || []) {
                this.notification.add("Nová žádost z webu: " + label, { type: "info" });
            }
        }
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
                iso, short: DNY_KRATCE[i], label: d.getDate() + ". " + (d.getMonth() + 1) + ".",
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
    async reject(item) {
        if (!confirm("Odmítnout rezervaci " + item.name + "? Klientovi odejde e-mail o zrušení.")) return;
        await this.orm.call("elite.vet.reservation", "action_cancel", [[item.id], "clinic"]);
        await this.load(true);
    }
}

registry.category("actions").add("elite_vet_reservation.board", ReservationBoard);
