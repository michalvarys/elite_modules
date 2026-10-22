/** Objednat: free times from the reservation wizard and a confirmed reservation for a pet. */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
import {
    BOARD_URL,
    BOOKING_SCREEN,
    callReception,
    clinicToday,
    dayLabel,
    shiftDay,
} from "@elite_vet_reception/pos/reception_api";

export class ReceptionBookingScreen extends Component {
    static template = "elite_vet_reception.BookingScreen";
    static props = {
        // {id, name, owner, partner_id} of the pet to book for (from the card index)
        pet: { type: Object, optional: true },
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
        });
        onWillStart(async () => {
            const options = await callReception(this.orm, this.notification, "booking_options");
            if (options) {
                this.state.procedures = options.procedures;
                this.state.doctors = options.doctors;
            }
        });
    }

    get pet() {
        return this.props.pet || null;
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
            }
        } finally {
            this.state.loading = false;
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
    }

    pickClient() {
        this.dialog.add(CardIndexDialog, {});
    }

    openBoard() {
        window.location = BOARD_URL;
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
                this.state.booked = result.label;
                this.state.note = "";
                this.notification.add(`Objednáno: ${this.pet.name}, ${result.label}.`, { type: "success" });
            }
        } finally {
            this.state.saving = false;
        }
        // booked or taken in the meantime: the list must show the current state
        await this.loadSlots();
    }
}

registry.category("pos_screens").add(BOOKING_SCREEN, ReceptionBookingScreen);
