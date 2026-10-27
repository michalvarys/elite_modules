/**
 * Tabule in the till: the day board of the consulting rooms in a large dialog above the POS
 * (the open order stays below it). Same data as the backend board (`board_data`): rooms as
 * columns, time axis, doctor shifts, reservations, blocks and the payment chip. A click on a
 * reservation opens its detail, a click into a free place opens Objednat prefilled, a reservation
 * can be dragged to another time / room (`move_reservation` → the board's `board_move`).
 */
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { MoveConfirmDialog, shortDayLabel } from "@elite_vet_reservation/move_dialog/move_dialog";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
import { BoardEventDialog } from "@elite_vet_reception/pos/board_dialog/board_event_dialog";
import {
    BOOKING_SCREEN,
    CLINIC_TZ,
    clinicToday,
    dayLabel,
    errorMessage,
    shiftDay,
} from "@elite_vet_reception/pos/reception_api";

const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;
const PX_PER_MIN = 1.6; // as the backend board: 15 min = 24 px
const BAND_W = 16; // doctor shift band on the left of a column
const BAND_GAP = 2;

function hhmm(minute) {
    return `${Math.floor(minute / 60)}:${String(minute % 60).padStart(2, "0")}`;
}

/** Minutes from midnight now in the clinic. */
function clinicNowMinute() {
    const now = luxon.DateTime.now().setZone(CLINIC_TZ);
    return now.hour * 60 + now.minute;
}

/** White text would be unreadable on a light colour (same rule as the backend board). */
function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) {
        return "#fff";
    }
    const n = parseInt(m[1], 16);
    const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.62 ? "#1e293b" : "#fff";
}

// Task 24: Vše | Web | Klinika, remembered by the browser. WinVet entries only in "Vše",
// blocks always (they are not bookings). Same rule as the backend board.
const SOURCE_FILTER_KEY = "elite_vet_reception.board_source_filter";
const SOURCE_FILTERS = [
    { key: "all", label: "Vše", title: "Všechny rezervace i záznamy z WinVetu" },
    { key: "web", label: "Web", title: "Jen rezervace z webu" },
    { key: "clinic", label: "Klinika", title: "Jen rezervace založené na klinice (bez záznamů z WinVetu)" },
];

function loadSourceFilter() {
    try {
        const value = localStorage.getItem(SOURCE_FILTER_KEY);
        return SOURCE_FILTERS.some((f) => f.key === value) ? value : "all";
    } catch {
        return "all";
    }
}

export class BoardDialog extends Component {
    static template = "elite_vet_reception.BoardDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        day: { type: String, optional: true }, // "YYYY-MM-DD", default today
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.gridRef = useRef("grid");
        this.hhmm = hhmm;
        this.state = useState({
            day: this.props.day || clinicToday(),
            data: null,
            error: null,
            loading: false,
            moving: false,
            drag: null, // {id} while a reservation is dragged
            now: clinicNowMinute(),
            sourceFilter: loadSourceFilter(),
        });
        this.onBusChange = () => this.load();
        onWillStart(() => this.load());
        onMounted(() => {
            this.pos.bus?.subscribe(BUS_MESSAGE, this.onBusChange);
            this.timer = setInterval(() => {
                if (!document.hidden) {
                    this.load();
                }
            }, POLL_MS);
            this.scrollToNow();
        });
        // after a day change the new day starts at "now" (today) or at its start
        onPatched(() => {
            if (this.scrollPending && this.state.data && this.gridRef.el) {
                this.scrollPending = false;
                this.scrollToNow();
            }
        });
        onWillUnmount(() => {
            this.pos.bus?.unsubscribe(BUS_MESSAGE, this.onBusChange);
            clearInterval(this.timer);
        });
    }

    // ------------------------------------------------------------------ data

    async load() {
        const day = this.state.day;
        this.state.loading = true;
        try {
            const data = await this.orm.call("elite.vet.reservation", "board_data", [day]);
            // a slow answer for a day the user already left must not overwrite the board
            if (day === this.state.day) {
                this.state.data = data;
                this.state.error = null;
                this.state.now = clinicNowMinute();
                this.failing = false;
            }
        } catch (error) {
            if (day === this.state.day) {
                if (!this.state.data) {
                    this.state.error = errorMessage(error);
                } else if (!this.failing) {
                    this.notification.add(errorMessage(error), { type: "danger" });
                }
            }
            this.failing = true;
        } finally {
            this.state.loading = false;
        }
    }

    goTo(day) {
        if (!day || day === this.state.day) {
            return;
        }
        this.state.day = day;
        this.state.data = null;
        this.state.error = null;
        this.scrollPending = true;
        this.load();
    }

    changeDay(delta) {
        this.goTo(delta ? shiftDay(this.state.day, delta) : clinicToday());
    }

    onDayInput(ev) {
        this.goTo(ev.target.value);
    }

    // ------------------------------------------------------------------ header

    get isToday() {
        return this.state.day === clinicToday();
    }

    get title() {
        return "Tabule";
    }

    get dayTitle() {
        const label = dayLabel(this.state.day);
        return this.isToday ? `Dnes, ${label}` : label;
    }

    // ------------------------------------------------------------------ geometry

    get axis() {
        return this.state.data.axis;
    }

    get rows() {
        const out = [];
        for (let m = this.axis.from; m < this.axis.to; m += this.state.data.step) {
            out.push(m);
        }
        return out;
    }

    get bodyHeight() {
        return this.height(this.axis.from, this.axis.to);
    }

    top(minute) {
        return (minute - this.axis.from) * PX_PER_MIN;
    }

    height(from, to) {
        return Math.max(12, (to - from) * PX_PER_MIN);
    }

    isOpen(room, minute) {
        return room.open.some(([from, to]) => from <= minute && minute < to);
    }

    get showNow() {
        return this.isToday && this.state.now >= this.axis.from && this.state.now <= this.axis.to;
    }

    scrollToNow() {
        const grid = this.gridRef.el;
        if (!grid || !this.state.data) {
            return;
        }
        const minute = this.showNow ? this.state.now : this.axis.from;
        grid.scrollTop = Math.max(0, this.top(minute) - 80);
    }

    // ------------------------------------------------------------------ events

    eventsFor(room) {
        return this.state.data.events.filter((e) => e.room_id === room.id && this.passesSourceFilter(e));
    }

    // ------------------------------------------------------------------ source (task 24)

    get sourceFilters() {
        return SOURCE_FILTERS;
    }

    isWeb(e) {
        return e.kind === "reservation" && e.source === "web";
    }

    originTitle(e) {
        const when = e.created_at ? `, ${e.created_at}` : "";
        if (this.isWeb(e)) {
            return `Z webu – objednal(a) se klient sám${when}`;
        }
        return e.created_by ? `Založil(a): ${e.created_by}${when}` : `Založeno na klinice${when}`;
    }

    passesSourceFilter(e) {
        const filter = this.state.sourceFilter;
        if (filter === "all" || e.kind === "block") {
            return true;
        }
        if (this.isWinvet(e)) {
            return false;
        }
        return filter === "web" ? this.isWeb(e) : !this.isWeb(e);
    }

    get hiddenCount() {
        if (!this.state.data) {
            return 0;
        }
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

    /** Blocks over all rooms (no room) are drawn in every column. */
    get globalBlocks() {
        return this.state.data.events.filter((e) => !e.room_id && e.kind === "block");
    }

    isWebBlock(e) {
        return e.kind === "block" && e.block_scope === "web";
    }

    isReservation(e) {
        return e.kind === "reservation";
    }

    /** Read-only entry of the WinVet calendar (elite_vet_winvet): no detail, no drag, no actions. */
    isWinvet(e) {
        return e.kind === "winvet";
    }

    winvetTitle(e) {
        const lines = [`Z WinVetu · ${e.time_label}`, this.eventLabel(e)];
        if (e.procedure) {
            lines.push(`Činnost: ${e.procedure}`);
        }
        if (e.winvet_title && e.winvet_title !== this.eventLabel(e)) {
            lines.push(`Ve WinVetu: ${e.winvet_title}`);
        }
        lines.push("Jen pro čtení – mění se ve WinVetu. Termín je obsazený.");
        return lines.join("\n");
    }

    winvetNoteTitle(n) {
        return `Z WinVetu, celý den: ${n.label}${n.activity ? "\nČinnost: " + n.activity : ""}\nJen poznámka – termíny neblokuje.`;
    }

    /** Only the main reservation moves; its second-room copy follows it. */
    isMovable(e) {
        return this.isReservation(e) && e.state === "confirmed" && !e.is_second_room;
    }

    isShort(e) {
        return e.end - e.start <= 15;
    }

    eventLabel(e) {
        if (e.kind === "block") {
            return e.name;
        }
        if (e.pet && e.owner) {
            return `${e.pet} (${e.owner})`;
        }
        return e.pet || e.owner || e.name;
    }

    eventTitle(e) {
        if (this.isWinvet(e)) {
            return this.winvetTitle(e);
        }
        if (e.kind === "block") {
            return `${e.time_label}\n${e.name}${this.isWebBlock(e) ? "\nJen web – recepce sem objednat smí." : ""}`;
        }
        const lines = [`${e.time_label} · ${this.eventLabel(e)}`];
        if (e.procedure) {
            lines.push(`Úkon: ${e.procedure}`);
        }
        if (e.doctor) {
            lines.push(`Lékařka: ${e.doctor}`);
        }
        if (e.linked) {
            lines.push(`Společný zákrok, také v: ${e.linked}`);
        }
        if (this.isReservation(e)) {
            lines.push(this.originTitle(e));
        }
        return lines.join("\n");
    }

    eventClass(e) {
        return {
            o_ev_board_block: e.kind === "block",
            o_ev_board_block_web: this.isWebBlock(e),
            o_ev_board_winvet: this.isWinvet(e),
            o_ev_board_from_web: this.isWeb(e),
            o_ev_board_muted: e.state === "done" || e.state === "no_show",
            o_ev_board_short: this.isShort(e),
            o_ev_board_dragging: this.state.drag?.id === e.id,
        };
    }

    bandStyle(d) {
        return (
            `top:${this.top(d.from)}px;height:${this.height(d.from, d.to)}px;` +
            `left:${BAND_GAP + d.lane * (BAND_W + BAND_GAP)}px;width:${BAND_W}px;background:${d.color}`
        );
    }

    eventLeft(room) {
        return 4 + (room.lanes || 0) * (BAND_W + BAND_GAP);
    }

    eventStyle(room, e) {
        let style = `top:${this.top(e.start)}px;height:${this.height(e.start, e.end)}px`;
        if (this.isWinvet(e)) {
            // grey hatched card, the WinVet colour as the left stripe (board_dialog.scss)
            return `${style};left:${this.eventLeft(room)}px;border-left:7px solid ${e.winvet_color || "#94a3b8"}`;
        }
        if (e.kind !== "block") {
            style += `;left:${this.eventLeft(room)}px;background:${e.color_hex};color:${textOn(e.color_hex)}`;
            // stripe in the colour of the doctor the client is booked with
            if (e.doctor_color) {
                style += `;border-left:7px solid ${e.doctor_color};box-shadow:inset 2px 0 0 #fff,0 1px 2px rgba(0,0,0,.15)`;
            }
        }
        return style;
    }

    paymentChip(e) {
        if (e.payment_state === "waiting" || e.payment_state === "partial") {
            const title = e.payment_state === "partial" ? "Částečně zaplaceno" : "Čeká na platbu v pokladně";
            return { cls: "o_ev_board_chip_waiting", text: "k pokladně", title };
        }
        if (e.payment_state === "paid") {
            return { cls: "o_ev_board_chip_paid", text: "zaplaceno", title: "Zaplaceno" };
        }
        return false;
    }

    // ------------------------------------------------------------------ clicks

    /** Minute of a pointer position in a column: click = start of the cell, drop = nearest step. */
    minuteAt(ev, column, floor) {
        const rect = column.getBoundingClientRect();
        const raw = this.axis.from + (ev.clientY - rect.top) / PX_PER_MIN;
        const step = this.state.data.step;
        const snapped = (floor ? Math.floor(raw / step) : Math.round(raw / step)) * step;
        return Math.min(Math.max(this.axis.from, snapped), this.axis.to - step);
    }

    /** A free place: close the board and open Objednat with the room, day and time. */
    onColumnClick(ev, room) {
        if (ev.target.closest(".o_ev_board_event:not(.o_ev_board_block_web)")) {
            return;
        }
        const minute = this.minuteAt(ev, ev.currentTarget, true);
        this.props.close();
        // the client picked in Objednat stays (the screen keeps its state)
        this.pos.showScreen(BOOKING_SCREEN, {
            prefill: { day: this.state.day, minute, room_id: room.id, room: room.name, key: Date.now() },
        });
    }

    openEvent(e) {
        if (!this.isReservation(e)) {
            return;
        }
        this.dialog.add(BoardEventDialog, {
            reservationId: e.id,
            onChanged: () => this.load(),
            onClient: (detail) => this.openClient(detail),
            onMove: (detail) => this.moveInBooking(detail),
        });
    }

    /** Kartotéka for the reservation ("Přiřadit k rezervaci"); the board stays open. */
    openClient(detail) {
        this.dialog.add(CardIndexDialog, {
            mode: "reservation",
            reservation: {
                reservation_id: detail.main_id,
                time: detail.time,
                procedure: detail.procedure,
                owner: detail.owner,
                partner_id: detail.partner_id,
                pet_id: detail.pet_id,
                pet_name: detail.pet_name,
            },
            onChanged: () => this.load(),
        });
    }

    /** Přesunout: Objednat in the move mode (free times of the reservation's procedure). */
    moveInBooking(detail) {
        this.props.close();
        this.pos.showScreen(BOOKING_SCREEN, {
            move: {
                reservation_id: detail.reservation_id,
                procedure_id: detail.procedure_id,
                doctor_id: detail.doctor_id,
                day: detail.date,
                label: `${detail.date_label} ${detail.time}`,
                pet_name: detail.pet_name,
                owner: detail.owner,
                procedure: detail.procedure,
                key: Date.now(),
            },
        });
    }

    // ------------------------------------------------------------------ drag & drop

    onDragStart(ev, e) {
        if (!this.isMovable(e)) {
            ev.preventDefault();
            return;
        }
        this.state.drag = { id: e.id };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(e.id));
    }

    onDragEnd() {
        this.state.drag = null; // a cancelled drag (Esc) must not complete a later drop
    }

    onDragOver(ev) {
        if (this.state.drag) {
            ev.preventDefault();
        }
    }

    async onDrop(ev, room) {
        ev.preventDefault();
        const drag = this.state.drag;
        this.state.drag = null;
        if (!drag || this.state.moving) {
            return;
        }
        const minute = this.minuteAt(ev, ev.currentTarget, false);
        // Request 25. 10.: the move happens only after the user confirms it; dropped back on the
        // same place = nothing to do. Cancel = nothing changes.
        const event = (this.state.data?.events || []).find((e) => e.id === drag.id);
        if (!event || (event.start === minute && (event.room_id || false) === room.id)) {
            return;
        }
        this.askMove(event, minute, room);
    }

    /** Task 25: "Přesunout Rex (Novák) z čt 29. 10. 9:00–9:20, Ordinace 1 na …?" with the date, time
     *  and room still editable (and the e-mail checkbox); the server message stays in the dialog. */
    askMove(event, minute, room) {
        const day = this.state.day;
        const rooms = (this.state.data.rooms || []).map((r) => ({ id: r.id, name: r.name }));
        const oldRoom = rooms.find((r) => r.id === event.room_id)?.name || "";
        const who = [event.pet, event.owner ? `(${event.owner})` : ""].filter(Boolean).join(" ") || event.name;
        this.dialog.add(MoveConfirmDialog, {
            title: "Přesunout rezervaci?",
            confirmLabel: "Přesunout",
            verb: "Přesunout",
            who,
            from: `${shortDayLabel(day)} ${event.time_label}${oldRoom ? ", " + oldRoom : ""}`,
            date: day,
            minute,
            roomId: room.id,
            rooms,
            duration: event.end - event.start,
            step: this.state.data.step,
            mailTo: event.mail_on_move || false,
            mailOnTimeChange: true,
            origDate: day,
            origMinute: event.start,
            origRoomId: event.room_id || false,
            mailText: `Klient dostane e-mail o změně termínu (${event.mail_on_move || ""}).`,
            mailLabel: "Poslat klientovi e-mail o změně",
            onConfirm: (values) => this.move(event.id, values),
        });
    }

    /** move_reservation -> success toast; an error is thrown back to the dialog (stays open). */
    async move(reservationId, { date, minute, endMinute, roomId, notify, force }) {
        this.state.moving = true;
        let result;
        try {
            result = await this.orm.call("elite.vet.reception", "move_reservation", [
                reservationId,
                date,
                minute,
                roomId,
                notify,
                endMinute,
                force,
            ]);
        } finally {
            this.state.moving = false;
        }
        if (result) {
            this.notification.add(
                `Přesunuto: ${result.pet_name || result.owner || "rezervace"} – ${result.date_label || ""} ${result.time}, ${result.room}.`,
                { type: "success" }
            );
        }
        if (date !== this.state.day) {
            this.goTo(date);
        } else {
            await this.load();
        }
    }
}
