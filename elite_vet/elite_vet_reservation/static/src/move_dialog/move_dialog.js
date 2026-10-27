/** @odoo-module **/
/**
 * Task 25: the confirm dialog after a drop on the board (move a reservation / confirm a web
 * request). The target date, time (booking step) and room come prefilled from the drop and can be
 * corrected before "Přesunout" / "Potvrdit"; the "z … na …" text follows the inputs. When the client
 * would get an e-mail, a checkbox (ticked by default) lets this one change go without it.
 * Task 28: the end time ("do") too – prefilled start + current duration, it moves with the start
 * (the duration is kept) and can be set on its own (longer / shorter visit).
 * `onConfirm({date, minute, endMinute, roomId, notify})` calls the server; an error (time not free,
 * no doctor on duty) is shown in the dialog, which stays open for another try. The doctor / room rule
 * (DoctorRuleError: nobody on duty who does the procedure, not done in that room) can be overridden:
 * "Přesto přesunout" calls onConfirm again with `force: true`. Used by the backend board
 * (elite_vet_reservation) and the till's board (elite_vet_reception, POS assets).
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

const WEEKDAY_ABBR = ["po", "út", "st", "čt", "pá", "so", "ne"];

function pad(n) {
    return String(n).padStart(2, "0");
}

/** 545 -> "09:05" (the value of an <input type="time">). */
function timeValue(minute) {
    return `${pad(Math.floor(minute / 60))}:${pad(minute % 60)}`;
}

/** "09:05" -> 545, or null. */
export function parseTime(value) {
    const m = /^(\d{1,2}):(\d{2})/.exec(value || "");
    if (!m) {
        return null;
    }
    const minute = Number(m[1]) * 60 + Number(m[2]);
    return minute >= 0 && minute < 1440 ? minute : null;
}

/** "9:05" as the server writes it. */
export function timeLabel(minute) {
    return `${Math.floor(minute / 60)}:${pad(minute % 60)}`;
}

/** "čt 29. 10." of "2026-10-29" (Czech, not the browser language). */
export function shortDayLabel(iso) {
    const [y, m, d] = (iso || "").split("-").map(Number);
    if (!y || !m || !d) {
        return "";
    }
    const weekday = (new Date(y, m - 1, d, 12).getDay() + 6) % 7;
    return `${WEEKDAY_ABBR[weekday]} ${d}. ${m}.`;
}

export function errorText(error) {
    return error?.data?.message || error?.message || String(error || "Nepodařilo se uložit.");
}

/** Did the server refuse only the doctor / room rule (it can be overridden with force)? */
export function isDoctorRuleError(error) {
    return Boolean(error?.data?.name?.endsWith(".DoctorRuleError"));
}

export class MoveConfirmDialog extends Component {
    static template = "elite_vet_reservation.MoveConfirmDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        confirmLabel: String,
        verb: String, // "Přesunout" | "Potvrdit žádost"
        who: String,
        from: { type: String, optional: true }, // "čt 29. 10. 9:00–9:20, Ordinace 1"
        date: String, // "YYYY-MM-DD"
        minute: Number,
        roomId: { type: [Number, Boolean], optional: true },
        rooms: Array, // [{id, name}]
        duration: Number,
        step: { type: Number, optional: true },
        // e-mail to the client: the address, the checkbox label and the sentence
        mailTo: { type: [String, Boolean], optional: true },
        mailLabel: { type: String, optional: true },
        mailText: { type: String, optional: true },
        // a move e-mails only when the date or the time changes (not another room at the same time)
        mailOnTimeChange: { type: Boolean, optional: true },
        // where the reservation is now (a move): the e-mail and "nothing changed" compare with it
        origDate: { type: String, optional: true },
        origMinute: { type: Number, optional: true },
        origRoomId: { type: [Number, Boolean], optional: true },
        onConfirm: Function,
    };

    setup() {
        this.origDate = this.props.origDate || this.props.date;
        this.origMinute = this.props.origMinute ?? this.props.minute;
        this.origRoomId = this.props.origRoomId ?? (this.props.roomId || false);
        // no duration known (a request without a procedure): one booking step
        const duration = this.props.duration > 0 ? this.props.duration : this.props.step || 15;
        this.origEnd = this.origMinute + duration;
        this.state = useState({
            date: this.props.date,
            time: timeValue(this.props.minute),
            endTime: timeValue(Math.min(this.props.minute + duration, 1439)),
            roomId: this.props.roomId || (this.props.rooms[0] && this.props.rooms[0].id) || false,
            notify: true,
            busy: false,
            error: "",
            canForce: false,
        });
    }

    get stepSeconds() {
        return (this.props.step || 15) * 60;
    }

    /** Minutes from midnight of the time input, or null. */
    get minute() {
        return parseTime(this.state.time);
    }

    /** Minutes from midnight of the end ("do") input, or null. */
    get endMinute() {
        return parseTime(this.state.endTime);
    }

    /** The end is after the start (both filled). */
    get endValid() {
        const minute = this.minute;
        const end = this.endMinute;
        return minute !== null && end !== null && end > minute;
    }

    get roomName() {
        return this.props.rooms.find((r) => r.id === this.state.roomId)?.name || "";
    }

    get targetText() {
        const minute = this.minute;
        if (minute === null || !this.state.date) {
            return "";
        }
        const end = this.endValid ? timeLabel(this.endMinute) : "?";
        return `${shortDayLabel(this.state.date)} ${timeLabel(minute)}–${end}, ${this.roomName}`;
    }

    get question() {
        const lines = [`${this.props.verb} ${this.props.who}`];
        if (this.props.from) {
            lines.push(`z ${this.props.from}`);
        }
        lines.push(`na ${this.targetText}?`);
        return lines.join("\n");
    }

    /** Would the client get an e-mail with the current inputs? */
    get mailApplies() {
        if (!this.props.mailTo) {
            return false;
        }
        if (this.props.mailOnTimeChange) {
            return this.state.date !== this.origDate || this.minute !== this.origMinute;
        }
        return true;
    }

    get unchanged() {
        return (
            this.props.mailOnTimeChange &&
            this.state.date === this.origDate &&
            this.minute === this.origMinute &&
            this.endMinute === this.origEnd &&
            this.state.roomId === this.origRoomId
        );
    }

    onDate(ev) {
        this.state.date = ev.target.value;
        this.state.error = "";
        this.state.canForce = false;
    }

    /** A new start moves the end with it (the duration stays); the end can then be changed. */
    onTime(ev) {
        const before = this.minute;
        const end = this.endMinute;
        this.state.time = ev.target.value;
        this.state.error = "";
        this.state.canForce = false;
        const after = this.minute;
        if (before !== null && after !== null && end !== null && end > before) {
            this.state.endTime = timeValue(Math.min(after + (end - before), 1439));
        }
    }

    onEndTime(ev) {
        this.state.endTime = ev.target.value;
        this.state.error = "";
        this.state.canForce = false;
    }

    onRoom(ev) {
        this.state.roomId = Number(ev.target.value) || false;
        this.state.error = "";
        this.state.canForce = false;
    }

    onNotify(ev) {
        this.state.notify = ev.target.checked;
    }

    get forceLabel() {
        return `Přesto ${this.props.confirmLabel.toLowerCase()}`;
    }

    async confirm(force = false) {
        if (this.state.busy) {
            return;
        }
        const minute = this.minute;
        if (minute === null || !this.state.date) {
            this.state.error = "Vyplňte datum a čas.";
            return;
        }
        if (this.endMinute === null) {
            this.state.error = "Vyplňte čas konce (do).";
            return;
        }
        if (!this.endValid) {
            this.state.error = "Konec musí být po začátku.";
            return;
        }
        if (!this.state.roomId) {
            this.state.error = "Vyberte ordinaci.";
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        this.state.canForce = false;
        try {
            await this.props.onConfirm({
                date: this.state.date,
                minute,
                endMinute: this.endMinute,
                roomId: this.state.roomId,
                notify: this.mailApplies ? this.state.notify : true,
                force,
            });
        } catch (error) {
            // time not free / no doctor on duty: the server's message, the dialog stays open
            this.state.error = errorText(error);
            this.state.canForce = !force && isDoctorRuleError(error);
            this.state.busy = false;
            return;
        }
        this.props.close();
    }
}
