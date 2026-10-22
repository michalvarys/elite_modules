/**
 * Objednat: free times from the reservation wizard and a confirmed reservation for a pet.
 * Opened from the board with `prefill` (a click into a free place: day, room, time - the time is
 * selected once a procedure is chosen and the time is free) or with `move` (Přesunout: the free
 * times of the reservation's procedure, the chosen one moves it with `move_reservation`).
 * The client and pet are picked in the field "Klient a zvíře" (Kartotéka in the booking mode).
 * After a booking the form is emptied (procedure, time, client, pet); day and doctor stay.
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
            slots: null,
            nextFreeDay: null,
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
            this.state.day = move.day >= clinicToday() ? move.day : clinicToday();
            await this.loadSlots();
        } else if (prefill) {
            this.state.move = null;
            this.state.moved = null;
            this.state.booked = null;
            const hh = `${Math.floor(prefill.minute / 60)}:${String(prefill.minute % 60).padStart(2, "0")}`;
            this.state.prefill = { ...prefill, label: hh, found: null };
            this.state.day = prefill.day;
            await this.loadSlots();
        }
    }

    get pet() {
        return this.state.pet;
    }

    get dayTitle() {
        return dayLabel(this.state.day);
    }

    get isPastDay() {
        return this.state.day < clinicToday();
    }

    get procedure() {
        return this.state.procedures.find((p) => p.id === Number(this.state.procedureId)) || null;
    }

    slotKey(slot) {
        return `${slot.minute}-${slot.room_id}`;
    }

    isSelected(slot) {
        return this.state.selected && this.slotKey(this.state.selected) === this.slotKey(slot);
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
        if (slot) {
            this.state.selected = slot;
        }
    }

    onProcedureChange(ev) {
        this.state.procedureId = ev.target.value;
        this.state.booked = null;
        this.loadSlots();
    }

    onDoctorChange(ev) {
        this.state.doctorId = ev.target.value;
        this.loadSlots();
    }

    onDayInput(ev) {
        if (ev.target.value) {
            this.state.day = ev.target.value;
            this.loadSlots();
        }
    }

    changeDay(delta) {
        this.state.day = delta ? shiftDay(this.state.day, delta) : clinicToday();
        this.loadSlots();
    }

    goNextFreeDay() {
        if (this.state.nextFreeDay) {
            this.state.day = this.state.nextFreeDay;
            this.loadSlots();
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

    /** After a booking: a fresh form for the next client; day and doctor stay. */
    resetForm() {
        this.state.procedureId = "";
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

    leaveMove() {
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
        await this.loadSlots();
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
        await this.loadSlots();
    }
}

registry.category("pos_screens").add(BOOKING_SCREEN, ReceptionBookingScreen);
