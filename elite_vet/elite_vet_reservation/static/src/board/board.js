/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";

const PX_PER_MIN = 1.6;   // 15 min = 24 px

function pad(n) { return String(n).padStart(2, "0"); }
function hhmm(min) { return pad(Math.floor(min / 60)) + ":" + pad(min % 60); }
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }

export class ReservationBoard extends Component {
    static template = "elite_vet_reservation.Board";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ date: isoDate(new Date()), data: null, loading: true, drag: null });
        onWillStart(() => this.load());
        // Recepce nechava tabuli otevrenou celý den, nove zadosti z webu se musi objevit bez F5.
        // Neuspesna obnova (vyprsela session, server nedostupny) nesmi kazdych 30 s hodit neosetreny reject.
        this.timer = setInterval(() => this.load(true).catch(() => {}), 30000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // ---------- data ----------
    async load(silent = false) {
        if (!silent) this.state.loading = true;
        const date = this.state.date;
        const data = await this.orm.call("elite.vet.reservation", "board_data", [date]);
        // Mezitim se mohl prepnout den; starsi odpoved by prepsala tabuli daty jineho dne.
        if (date !== this.state.date) return;
        this.state.data = data;
        this.state.loading = false;
    }
    shiftDay(delta) {
        // Poledne, aby posun o den nepreskocil kvuli zmene letniho casu.
        const d = new Date(this.state.date + "T12:00:00");
        d.setDate(d.getDate() + delta);
        this.state.date = isoDate(d);
        this.load();
    }
    today() { this.state.date = isoDate(new Date()); this.load(); }
    onDateInput(ev) { if (ev.target.value) { this.state.date = ev.target.value; this.load(); } }

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
    get globalBlocks() { return this.state.data.events.filter((e) => !e.room_id); }
    minuteFromDrop(ev, column) {
        const rect = column.getBoundingClientRect();
        const y = ev.clientY - rect.top + column.scrollTop;
        const raw = this.axis.from + y / PX_PER_MIN;
        const step = this.state.data.step;
        return Math.max(this.axis.from, Math.round(raw / step) * step);
    }

    // ---------- interakce ----------
    openForm(resId, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "elite.vet.reservation", res_id: resId || false,
            views: [[false, "form"]], target: "new", context,
        }, { onClose: () => this.load(true) });
    }
    async newAt(room, min) {
        const start = await this.orm.call("elite.vet.reservation", "board_slot_utc", [this.state.date, min]);
        this.openForm(false, { default_room_id: room.id, default_start: start, default_kind: "reservation", default_state: "confirmed" });
    }
    newBlock() { this.openForm(false, { default_kind: "block", default_state: "confirmed" }); }
    onColumnClick(ev, room) {
        if (ev.target.closest(".evb-event")) return;
        this.newAt(room, this.minuteFromDrop(ev, ev.currentTarget));
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
    async reject(item) {
        if (!confirm("Odmítnout rezervaci " + item.name + "? Klientovi odejde e-mail o zrušení.")) return;
        await this.orm.call("elite.vet.reservation", "action_cancel", [[item.id], "clinic"]);
        await this.load(true);
    }
}

registry.category("actions").add("elite_vet_reservation.board", ReservationBoard);
