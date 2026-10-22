/**
 * Objednat: free times from the reservation wizard and a confirmed reservation for a pet.
 * Opened from the board with `prefill` (a click into a free place: day, room, time - the time is
 * selected once a procedure is chosen and the time is free) or with `move` (Přesunout: the free
 * times of the reservation's procedure, the chosen one moves it with `move_reservation`).
 * One column of steps: client and pet (an inline search, `booking_search`; Kartotéka in the
 * booking mode for a new client, a new pet or Upravit), procedure (the frequent ones as buttons,
 * "Jiný úkon…" for the rest), day (a strip of seven days with the number of free times or
 * "zavřeno", `free_days`; above it the nearest free time in one click, `nearest_free`), room
 * (only when more than one has free times) and time (morning / afternoon), then a one-line
 * summary above the only button. The doctor is an optional filter ("jen lékařka…"). After a
 * procedure or doctor change the strip jumps to its first day with free times when the selected
 * day has none. After a booking the form is emptied (everything but the day). The "Objednáno"
 * message stays until the next booking is started.
 */
import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";
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

const CLIENT_SEARCH_DELAY = 300; // ms after the last key before the inline search runs

/** Lower case without diacritics, for the procedure filter. */
function plain(text) {
    return (text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

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
            frequent: [], // ids of the frequent procedures (buttons of step Úkon)
            showAllProcedures: false, // "Jiný úkon…" list open
            procedureFilter: "",
            clientSearch: false, // inline client search open although a pet is selected (Změnit)
            clientTerm: "",
            clientResults: null, // booking_search rows of clientTerm
            clientSearching: false,
            nearest: null, // nearest_free of the procedure / doctor
            nearestLoaded: false,
            pick: null, // {day, minute, room_id}: the nearest time, selected once its day is loaded
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
        this.clientInput = useRef("clientInput");
        this.clientTimer = null;
        useEffect(
            (open) => {
                if (open) {
                    this.clientInput.el?.focus();
                }
            },
            () => [this.showClientSearch]
        );
        onWillUnmount(() => clearTimeout(this.clientTimer));
        onWillStart(async () => {
            const options = await callReception(this.orm, this.notification, "booking_options");
            if (options) {
                this.state.procedures = options.procedures;
                this.state.doctors = options.doctors;
                this.state.frequent = options.frequent || [];
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
            await this.reloadAll({ jump: true });
        } else if (prefill) {
            this.state.move = null;
            this.state.moved = null;
            this.state.booked = null;
            const hh = `${Math.floor(prefill.minute / 60)}:${String(prefill.minute % 60).padStart(2, "0")}`;
            this.state.prefill = { ...prefill, label: hh, found: null };
            this.state.day = this.state.weekStart = prefill.day;
            await this.reloadAll();
        }
    }

    get pet() {
        return this.state.pet;
    }

    /** Step 1 shows the search field (no pet yet, or Změnit). */
    get showClientSearch() {
        return !this.state.move && (!this.pet || this.state.clientSearch);
    }

    /** Buttons of step Úkon: the frequent procedures, plus the selected one when it is not frequent. */
    get procedureChips() {
        const byId = new Map(this.state.procedures.map((p) => [p.id, p]));
        const chips = this.state.frequent.map((id) => byId.get(id)).filter(Boolean);
        const selected = this.procedure;
        if (selected && !chips.includes(selected)) {
            chips.push(selected);
        }
        return chips;
    }

    /** All procedures for "Jiný úkon…", filtered by the typed text. */
    get filteredProcedures() {
        const term = plain(this.state.procedureFilter.trim());
        return term ? this.state.procedures.filter((p) => plain(p.name).includes(term)) : this.state.procedures;
    }

    /** The strip item of the selected day ({day, count, closed}) or null. */
    get currentDay() {
        return (this.state.days || []).find((d) => d.day === this.state.day) || null;
    }

    /** "dnes 14:30 · Ordinace 2 · MVDr. Malá" of the nearest free time. */
    get nearestLabel() {
        const nearest = this.state.nearest;
        if (!nearest) {
            return "";
        }
        const today = clinicToday();
        const day =
            nearest.day === today ? "dnes" : nearest.day === shiftDay(today, 1) ? "zítra" : this.shortDayLabel(nearest.day);
        return [`${day} ${nearest.time}`, nearest.room, nearest.doctor].filter(Boolean).join(" · ");
    }

    /** "Rex (pes) · Jana Nováková · 777 123 456" of a row of the inline search. */
    clientRowLabel(row) {
        const pet = row.kind === "pet" ? (row.species_label ? `${row.name} (${row.species_label.toLowerCase()})` : row.name) : null;
        return [pet, row.owner, row.phone].filter(Boolean).join(" · ");
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
                this.selectPicked();
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

    /** The nearest time picked with the button, once the slots of its day are loaded. */
    selectPicked() {
        const pick = this.state.pick;
        if (!pick || pick.day !== this.state.day || !this.state.slots) {
            return;
        }
        this.state.pick = null;
        const slot = this.state.slots.find((s) => s.minute === pick.minute && s.room_id === pick.room_id);
        if (slot) {
            this.state.roomId = slot.room_id;
            this.selectSlot(slot);
        } else {
            this.notification.add("Tento čas mezitím někdo obsadil – vyberte jiný.", { type: "warning" });
            this.loadNearest();
        }
    }

    /** Nearest free time of the procedure (and the doctor filter). */
    async loadNearest() {
        this.state.nearest = null;
        this.state.nearestLoaded = false;
        if (!this.state.procedureId) {
            return;
        }
        const request = [Number(this.state.procedureId), Number(this.state.doctorId) || false];
        const data = await callReception(this.orm, this.notification, "nearest_free", request);
        const current = [Number(this.state.procedureId), Number(this.state.doctorId) || false];
        if (JSON.stringify(request) === JSON.stringify(current)) {
            this.state.nearest = data || null;
            this.state.nearestLoaded = data !== undefined;
        }
    }

    /**
     * Strip, times and the nearest time again (procedure / doctor change, the move mode, the
     * board prefill). With `jump` a selected day without free times is left for the first day of
     * the strip that has some (not with the board prefill: its day was clicked).
     */
    async reloadAll({ jump = false } = {}) {
        const nearest = this.loadNearest();
        await Promise.all([this.loadDays(), this.loadSlots()]);
        if (jump && !this.state.prefill) {
            const current = this.currentDay;
            const free = (this.state.days || []).find((d) => d.count);
            if (current && !current.count && free) {
                this.selectDay(free.day);
            }
        }
        await nearest;
    }

    /** The day, room and time of the nearest free time (the strip moves to its week). */
    pickNearest() {
        const nearest = this.state.nearest;
        if (!nearest) {
            return;
        }
        this.state.prefill = null;
        this.state.pick = { day: nearest.day, minute: nearest.minute, room_id: nearest.room_id };
        if (!(this.state.days || []).some((d) => d.day === nearest.day)) {
            this.state.weekStart = nearest.day;
            this.loadDays();
        }
        this.state.roomId = nearest.room_id;
        this.selectDay(nearest.day);
    }

    selectProcedure(procedureId) {
        this.state.procedureId = String(procedureId);
        this.state.showAllProcedures = false;
        this.state.procedureFilter = "";
        this.state.booked = null;
        this.reloadAll({ jump: true });
    }

    toggleAllProcedures() {
        this.state.showAllProcedures = !this.state.showAllProcedures;
        this.state.procedureFilter = "";
    }

    onDoctorChange(ev) {
        this.state.doctorId = ev.target.value;
        this.state.booked = null;
        this.reloadAll({ jump: true });
    }

    clearDoctor() {
        this.state.doctorId = "";
        this.state.showDoctor = false;
        this.state.booked = null;
        this.reloadAll({ jump: true });
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

    // ------------------------------------------------------------------ step 1: client and pet

    onClientInput(ev) {
        this.state.clientTerm = ev.target.value;
        clearTimeout(this.clientTimer);
        if (this.state.clientTerm.trim().length < 2) {
            this.state.clientResults = null;
            return;
        }
        this.clientTimer = setTimeout(() => this.searchClients(), CLIENT_SEARCH_DELAY);
    }

    /** Enter: search at once; with results already shown the first row is taken. */
    onClientKeydown(ev) {
        if (ev.key === "Escape" && this.pet) {
            this.closeClientSearch();
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const results = this.state.clientResults;
            if (results && results.length && !this.state.clientSearching) {
                this.pickClientRow(results[0]);
            } else {
                clearTimeout(this.clientTimer);
                this.searchClients();
            }
        }
    }

    async searchClients() {
        const term = this.state.clientTerm.trim();
        if (term.length < 2) {
            return;
        }
        this.state.clientSearching = true;
        try {
            const rows = await callReception(this.orm, this.notification, "booking_search", [term]);
            if (rows && term === this.state.clientTerm.trim()) {
                this.state.clientResults = rows;
            }
        } finally {
            this.state.clientSearching = false;
        }
    }

    setPet(pet) {
        this.state.pet = pet;
        this.state.booked = null;
        this.closeClientSearch();
    }

    /** A pet row selects it; an owner without a live pet opens Kartotéka to add one. */
    pickClientRow(row) {
        if (row.kind === "pet") {
            this.setPet({ id: row.id, name: row.name, owner: row.owner, partner_id: row.partner_id });
        } else {
            this.openCardIndex({ client: { partner_id: row.partner_id }, start: "new_pet" });
        }
    }

    /** Změnit: the inline search again (the selected pet stays until another one is taken). */
    openClientSearch() {
        this.state.clientSearch = true;
        this.state.clientTerm = "";
        this.state.clientResults = null;
    }

    closeClientSearch() {
        clearTimeout(this.clientTimer);
        this.state.clientSearch = false;
        this.state.clientTerm = "";
        this.state.clientResults = null;
    }

    /** Kartotéka in the booking mode; its Vybrat fills step 1. */
    openCardIndex(props = {}) {
        this.dialog.add(CardIndexDialog, {
            mode: "booking",
            ...props,
            onSelect: (picked) => this.setPet(picked),
        });
    }

    /** + Nový klient: the new-client form of Kartotéka. */
    newClient() {
        this.openCardIndex({ start: "new_owner" });
    }

    /** Upravit: Kartotéka on the selected client and pet. */
    editClient() {
        const pet = this.pet;
        if (pet) {
            this.openCardIndex({ client: { partner_id: pet.partner_id, pet_id: pet.id } });
        }
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
        this.state.showAllProcedures = false;
        this.state.procedureFilter = "";
        this.state.nearest = null;
        this.state.nearestLoaded = false;
        this.state.pick = null;
        this.closeClientSearch();
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
            this.state.nearest = null;
            this.state.nearestLoaded = false;
            this.state.pick = null;
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
        await this.reloadAll();
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
        await this.reloadAll();
    }
}

registry.category("pos_screens").add(BOOKING_SCREEN, ReceptionBookingScreen);
