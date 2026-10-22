/**
 * Objednat: free times from the reservation wizard and a confirmed reservation for a pet.
 * Opened from the board with `prefill` (a click into a free place: day, room, time - the time is
 * selected once a procedure is chosen and the time is free) or with `move` (Přesunout: the free
 * times of the reservation's procedure, the chosen one moves it with `move_reservation`).
 * One column of steps: client and pet (Kartotéka in the booking mode), procedure, day (a strip of
 * seven days with the number of free times, `free_days`), room (only when more than one has free
 * times) and time (morning / afternoon), then a one-line summary above the only button.
 * The doctor is an optional filter ("jen lékařka…"). After a booking the form is emptied
 * (everything but the day). The "Objednáno" message stays until the next booking is started.
 */
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
import { BoardDialog } from "@elite_vet_reception/pos/board_dialog/board_dialog";
import {
    BOOKING_SCREEN,
    callReception,
    clinicToday,
    dayLabel,
    shiftDay,
} from "@elite_vet_reception/pos/reception_api";

export class ReceptionBookingScreen extends Component {
    static template = "elite_vet_reception.BookingScreen";
    static props = {
        // {id, name, owner, partner_id} of the pet to book for (initial value of the field)
        pet: { type: Object, optional: true },
        // navbar Objednat pressed while the screen is shown: {key} - leaves the move mode
        reset: { type: Object, optional: true },
        // from the board, a click into a free place: {day, minute, room_id, room, key}
        prefill: { type: Object, optional: true },
        // from the board, Přesunout: {reservation_id, procedure_id, doctor_id, day, label, pet_name,
        // owner, procedure, key}
        move: { type: Object, optional: true },
    };
    static storeOnOrder = false;

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.dayLabel = dayLabel;
        this.state = useState({
            procedures: [],
            doctors: [],
            pet: this.props.pet || null, // {id, name, owner, partner_id}
            procedureId: "",
            doctorId: "",
            day: clinicToday(),
            weekStart: clinicToday(), // first day of the day strip
            days: null, // [{day, count}] of the strip (free_days)
            showDoctor: false, // the doctor filter select is open
            slots: null,
            nextFreeDay: null,
            roomId: null, // chosen room (kept over day changes; shown only while it has free times)
            selected: null,
            note: "",
            loading: false,
            saving: false,
            booked: null,
            prefill: null, // {day, minute, room_id, room, label, found: null | true | false}
            move: null, // props.move while the move mode lasts
            moved: null, // label of the done move
        });
        onWillStart(async () => {
            const options = await callReception(this.orm, this.notification, "booking_options");
            if (options) {
                this.state.procedures = options.procedures;
                this.state.doctors = options.doctors;
            }
            await this.applyBoardProps(this.props);
        });
        // the POS keeps this screen and only changes its props when it is shown again
        onWillUpdateProps((next) => {
            const changed = (key) => next[key] && next[key].key !== this.props[key]?.key;
            if (changed("prefill") || changed("move")) {
                this.applyBoardProps(next);
            } else if (changed("reset")) {
                this.leaveMove();
                this.state.prefill = null;
            }
        });
    }

    /** Prefill from the board (free place) or the move mode (Přesunout). */
    async applyBoardProps(props) {
        const { prefill, move } = props;
        if (move) {
            this.state.move = move;
            this.state.moved = null;
            this.state.prefill = null;
            this.state.booked = null;
            if (this.state.procedures.some((p) => p.id === move.procedure_id)) {
                this.state.procedureId = String(move.procedure_id);
            }
            const doctorKnown = this.state.doctors.some((d) => d.id === move.doctor_id);
            this.state.doctorId = doctorKnown ? String(move.doctor_id) : "";
            this.state.day = this.state.weekStart = move.day >= clinicToday() ? move.day : clinicToday();
            await Promise.all([this.loadDays(), this.loadSlots()]);
        } else if (prefill) {
            this.state.move = null;
            this.state.moved = null;
            this.state.booked = null;
            const hh = `${Math.floor(prefill.minute / 60)}:${String(prefill.minute % 60).padStart(2, "0")}`;
            this.state.prefill = { ...prefill, label: hh, found: null };
            this.state.day = this.state.weekStart = prefill.day;
            await Promise.all([this.loadDays(), this.loadSlots()]);
        }
    }

    get pet() {
        return this.state.pet;
    }

    get dayTitle() {
        return dayLabel(this.state.day);
    }

    get doctor() {
        return this.state.doctors.find((d) => d.id === Number(this.state.doctorId)) || null;
    }

    get canGoBack() {
        return this.state.weekStart > clinicToday();
    }

    /** "Rex · Kontrola · čt 22. 10. 2026 9:30 · Ordinace 2 · MVDr. Malá" once a time is chosen. */
    get summary() {
        const slot = this.state.selected;
        if (!slot) {
            return "";
        }
        const who = this.state.move ? this.state.move.pet_name || this.state.move.owner : this.pet?.name;
        return [who, this.procedure?.name, `${dayLabel(this.state.day)} ${slot.time}`, slot.room, slot.doctor]
            .filter(Boolean)
            .join(" · ");
    }

    /** Step numbers: without the client step (move mode) every step is one lower. */
    stepNo(number) {
        return this.state.move ? number - 1 : number;
    }

    /** "čt 22. 10." */
    shortDayLabel(isoDay) {
        return luxon.DateTime.fromISO(isoDay).setLocale("cs").toFormat("ccc d. L.");
    }

    /** The times split into morning and afternoon (empty parts left out). */
    dayParts(slots) {
        const parts = [
            { name: "Dopoledne", slots: slots.filter((slot) => slot.minute < 12 * 60) },
            { name: "Odpoledne", slots: slots.filter((slot) => slot.minute >= 12 * 60) },
        ];
        return parts.filter((part) => part.slots.length);
    }

    get isPastDay() {
        return this.state.day < clinicToday();
    }

    get procedure() {
        return this.state.procedures.find((p) => p.id === Number(this.state.procedureId)) || null;
    }

    /** Rooms with free times (natural name order), each with its `slots`; `doctor` is set when the
     *  whole room has the same doctor. */
    get rooms() {
        const groups = new Map();
        for (const slot of this.state.slots || []) {
            if (!groups.has(slot.room_id)) {
                groups.set(slot.room_id, { room_id: slot.room_id, room: slot.room, slots: [] });
            }
            groups.get(slot.room_id).slots.push(slot);
        }
        for (const group of groups.values()) {
            // one doctor for the whole room: shown once in the heading, not on every time
            const doctors = new Set(group.slots.map((slot) => slot.doctor || ""));
            group.doctor = doctors.size === 1 ? group.slots[0].doctor : null;
        }
        return [...groups.values()].sort((a, b) =>
            (a.room || "").localeCompare(b.room || "", "cs", { numeric: true })
        );
    }

    /** The room whose times are shown: the only one, or the chosen one (null = choose first). */
    get activeRoom() {
        const rooms = this.rooms;
        if (rooms.length === 1) {
            return rooms[0];
        }
        return rooms.find((room) => room.room_id === this.state.roomId) || null;
    }

    freeLabel(count) {
        const word = count === 1 ? "volný" : count >= 2 && count <= 4 ? "volné" : "volných";
        return `${count} ${word}`;
    }

    selectRoom(room) {
        this.state.roomId = room.room_id;
        this.state.booked = null;
        this.state.moved = null;
        if (this.state.selected && this.state.selected.room_id !== room.room_id) {
            this.state.selected = null;
            this.state.prefill = null;
        }
    }

    slotKey(slot) {
        return `${slot.minute}-${slot.room_id}`;
    }

    isSelected(slot) {
        return this.state.selected && this.slotKey(this.state.selected) === this.slotKey(slot);
    }

    /** Free times per day of the strip (weekStart + 6 days). */
    async loadDays() {
        if (!this.state.procedureId) {
            this.state.days = null;
            return;
        }
        const request = [Number(this.state.procedureId), this.state.weekStart, Number(this.state.doctorId) || false];
        const data = await callReception(this.orm, this.notification, "free_days", request);
        const current = [Number(this.state.procedureId), this.state.weekStart, Number(this.state.doctorId) || false];
        if (data && JSON.stringify(request) === JSON.stringify(current)) {
            this.state.days = data;
        }
    }

    async loadSlots() {
        this.state.selected = null;
        if (!this.state.procedureId) {
            this.state.slots = null;
            this.state.nextFreeDay = null;
            return;
        }
        const request = [Number(this.state.procedureId), this.state.day, Number(this.state.doctorId) || false];
        this.state.loading = true;
        try {
            const data = await callReception(this.orm, this.notification, "free_slots", request);
            const current = [Number(this.state.procedureId), this.state.day, Number(this.state.doctorId) || false];
            if (data && JSON.stringify(request) === JSON.stringify(current)) {
                this.state.slots = data.slots;
                this.state.nextFreeDay = data.next_free_day;
                this.selectPrefilled();
            }
        } finally {
            this.state.loading = false;
        }
    }

    /** The time clicked on the board, when it is free for the chosen procedure. */
    selectPrefilled() {
        const prefill = this.state.prefill;
        if (!prefill || prefill.day !== this.state.day || !this.state.slots) {
            return;
        }
        const slot = this.state.slots.find((s) => s.minute === prefill.minute && s.room_id === prefill.room_id);
        prefill.found = Boolean(slot);
        if (this.state.slots.some((s) => s.room_id === prefill.room_id)) {
            this.state.roomId = prefill.room_id;
        }
        if (slot) {
            this.state.selected = slot;
        }
    }

    onProcedureChange(ev) {
        this.state.procedureId = ev.target.value;
        this.state.booked = null;
        this.loadDays();
        this.loadSlots();
    }

    onDoctorChange(ev) {
        this.state.doctorId = ev.target.value;
        this.state.booked = null;
        this.loadDays();
        this.loadSlots();
    }

    clearDoctor() {
        this.state.doctorId = "";
        this.state.showDoctor = false;
        this.state.booked = null;
        this.loadDays();
        this.loadSlots();
    }

    selectDay(day) {
        this.state.day = day;
        this.state.booked = null;
        this.loadSlots();
    }

    /** Another date from the calendar: the strip starts there. */
    onDayInput(ev) {
        if (ev.target.value) {
            this.state.day = this.state.weekStart = ev.target.value < clinicToday() ? clinicToday() : ev.target.value;
            this.state.booked = null;
            this.loadDays();
            this.loadSlots();
        }
    }

    /** ‹ › of the strip: a week back / forward, the first day with free times gets selected. */
    async shiftWeek(delta) {
        const start = shiftDay(this.state.weekStart, delta);
        this.state.weekStart = start < clinicToday() ? clinicToday() : start;
        this.state.booked = null;
        await this.loadDays();
        const free = (this.state.days || []).find((d) => d.count);
        this.selectDay(free ? free.day : this.state.weekStart);
    }

    goNextFreeDay() {
        const next = this.state.nextFreeDay;
        if (next) {
            const inStrip = (this.state.days || []).some((d) => d.day === next);
            if (!inStrip) {
                this.state.weekStart = next;
                this.loadDays();
            }
            this.selectDay(next);
        }
    }

    selectSlot(slot) {
        this.state.selected = slot;
        this.state.booked = null;
        this.state.moved = null;
        const prefill = this.state.prefill;
        if (prefill && (slot.minute !== prefill.minute || slot.room_id !== prefill.room_id)) {
            this.state.prefill = null; // another time than the one from the board
        }
    }

    /** Field "Klient a zvíře": Kartotéka in the booking mode, Vybrat fills the field. */
    pickClient() {
        const pet = this.pet;
        this.dialog.add(CardIndexDialog, {
            mode: "booking",
            ...(pet ? { client: { partner_id: pet.partner_id, pet_id: pet.id } } : {}),
            onSelect: (picked) => {
                this.state.pet = picked;
                this.state.booked = null;
            },
        });
    }

    /** After a booking: a fresh form for the next client; only the day stays. */
    resetForm() {
        this.state.procedureId = "";
        this.state.doctorId = "";
        this.state.showDoctor = false;
        this.state.days = null;
        this.state.roomId = null;
        this.state.selected = null;
        this.state.slots = null;
        this.state.nextFreeDay = null;
        this.state.pet = null;
        this.state.note = "";
        this.state.prefill = null;
    }

    openBoard() {
        this.dialog.add(BoardDialog, { day: this.state.day });
    }

    /**
     * Nepřesouvat / navbar Objednat: back to a plain booking form. The time and the procedure of
     * the moved reservation are dropped, so a click cannot book a new reservation at the move slot.
     */
    leaveMove() {
        if (this.state.move) {
            this.state.procedureId = "";
            this.state.roomId = null;
            this.state.selected = null;
            this.state.slots = null;
            this.state.days = null;
            this.state.nextFreeDay = null;
        }
        this.state.move = null;
        this.state.moved = null;
    }

    async moveReservation() {
        const slot = this.state.selected;
        const move = this.state.move;
        if (!slot || !move || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "move_reservation", [
                move.reservation_id,
                this.state.day,
                slot.minute,
                slot.room_id,
            ]);
            if (result) {
                const label = `${result.date_label} ${result.time}, ${result.room}`;
                this.state.move = null;
                this.state.moved = label;
                this.notification.add(`Přesunuto: ${result.pet_name || result.owner || "rezervace"} – ${label}.`, {
                    type: "success",
                });
            }
        } finally {
            this.state.saving = false;
        }
        await Promise.all([this.loadDays(), this.loadSlots()]);
    }

    async book() {
        const slot = this.state.selected;
        if (!slot || !this.pet || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "book", [
                this.pet.id,
                Number(this.state.procedureId),
                this.state.day,
                slot.minute,
                slot.room_id,
                Number(this.state.doctorId) || false,
                this.state.note,
            ]);
            if (result) {
                const text = `${dayLabel(this.state.day)} ${slot.time} · ${this.pet.name}`;
                this.resetForm();
                this.state.booked = text;
                this.notification.add(`Objednáno: ${text}`, { type: "success" });
                return;
            }
        } finally {
            this.state.saving = false;
        }
        // taken in the meantime: the list must show the current state
        await Promise.all([this.loadDays(), this.loadSlots()]);
    }
}

registry.category("pos_screens").add(BOOKING_SCREEN, ReceptionBookingScreen);
