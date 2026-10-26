/** @odoo-module **/
// Screen Ordinace (task 15, client action elite_vet_reception.room_board): the visits of the day
// by consultation room. Top switch Všechny ordinace | <room> …:
// - Všechny ordinace: columns Nepřiřazení + one per room; arrived patients are dragged between
//   columns (or "…" › Do jiné ordinace on touch screens).
// - one room: the flow Dnes jsou objednaní | Čekají | V ordinaci (Hotovo dnes folded under the
//   last one; stacked on narrow screens: Čekají, V ordinaci, Dnes jsou objednaní – CSS order),
//   above it one bar with the unassigned patients: Vzít dalšího / Zobrazit.
// Task 26: one design system (.ev-clinic, elite_vet_clinic/static/src/clinic_ui), every patient
// is the shared visit tile with one primary action by state and the rest in the "…" menu.
// Data: elite.vet.reception.room_board (models/room_board.py, shapes in README.md).
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { plural, visitTile } from "@elite_vet_clinic/clinic_ui/clinic_ui";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";

const RECEPTION = "elite.vet.reception";
const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;
const VIEW_KEY = "elite_vet_reception.room_view";   // remembered choice of this browser
const ALL = "all";
// Všechny ordinace: a tile text longer than this may be clamped (2–3 lines) -> tooltip
const TILE_TEXT_CLAMP = 40;

// Left to right in the room, top to bottom in a column of Všechny ordinace; Hotovo is folded
// under the last one. Feedback 26. 10.: the day reads from the booked ones to the room.
export const ROOM_SECTIONS = [
    { key: "booked", title: "Dnes jsou objednaní", hint: "ještě nepřišli", empty: "Všichni objednaní už přišli." },
    { key: "waiting", title: "Čekají", empty: "Nikdo nečeká." },
    { key: "in_room", title: "V ordinaci", empty: "V ordinaci nikdo není." },
];

function errorMessage(e) { return e?.data?.message || e?.message || String(e); }

function loadView() {
    try {
        return localStorage.getItem(VIEW_KEY) || null;
    } catch {
        return null;
    }
}
function saveView(view) {
    try {
        localStorage.setItem(VIEW_KEY, String(view));
    } catch {
        // private window / blocked storage: the choice is just not remembered
    }
}

/** Poznámka recepce of a visit (set_reception_note), from the "…" menu. */
export class RoomNoteDialog extends Component {
    static template = "elite_vet_reception.RoomNoteDialog";
    static components = { Dialog };
    static props = ["item", "onSave", "close"];

    setup() {
        this.state = useState({ note: this.props.item.reception_note || "", busy: false });
    }
    async save() {
        this.state.busy = true;
        try {
            if (await this.props.onSave(this.state.note)) this.props.close();
        } finally {
            this.state.busy = false;
        }
    }
}

/** The "…" menu of a tile: its own component, so every item keeps its own patient. */
export class RoomMenu extends Component {
    static template = "elite_vet_reception.RoomMenu";
    static components = { Dropdown, DropdownItem };
    static props = ["it", "board"];
}

export class RoomBoard extends Component {
    static template = "elite_vet_reception.RoomBoard";
    static components = { RoomMenu };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            data: null, loading: true, view: ALL, busy: false,
            drag: null,          // key of the dragged card
            dropKey: null,       // column under the dragged card
            pickDoctor: null,    // {item, roomId, doctors}: two doctors on duty, who takes it
            openDone: {},        // column key -> Hotovo expanded
            showUnassigned: false,   // one room: the unassigned list under the bar
        });
        const action = this.props.action || {};
        const params = action.params || action.context?.params || {};
        this.paramRoomId = parseInt(params.room_id || 0, 10) || null;
        // the switch as it was when the user left the screen (back through the breadcrumbs)
        this.restoredView = this.props.state?.roomView ?? null;
        useSetupAction({ getLocalState: () => ({ roomView: this.state.view }) });

        onWillStart(async () => {
            await this.load();
            this.state.view = this.initialView();
            this.state.loading = false;
        });
        this.busService = useService("bus_service");
        this.onBusChange = () => this.refresh();
        this.busService.subscribe(BUS_MESSAGE, this.onBusChange);
        this.busService.start();
        // fallback when the websocket is down
        this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, POLL_MS);
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.busService.unsubscribe(BUS_MESSAGE, this.onBusChange);
        });
    }

    // ------------------------------------------------------------ data
    async load() {
        this.state.data = await this.orm.call(RECEPTION, "room_board", []);
    }
    refresh() {
        if (this.state.drag || this.state.busy) return;
        this.load().catch(() => {});
    }
    /** A room account opens its own room every time. An account of a team member (task 23)
     *  opens the room of her duty now (else her next duty today, else Všechny ordinace) on every
     *  open; her switch holds while she works in the screen (also back from a card) and is not
     *  stored in the browser. Others get the choice remembered by this browser. */
    initialView() {
        const data = this.state.data;
        const perms = data.perms;
        const ids = new Set(data.rooms.map((r) => r.id));
        const valid = (view) => view === ALL || ids.has(view);
        if (this.paramRoomId && ids.has(this.paramRoomId)) return this.paramRoomId;
        if (perms.user_room_id && ids.has(perms.user_room_id)) return perms.user_room_id;
        if (this.restoredView !== null && valid(this.restoredView)) return this.restoredView;
        if (perms.member_account) {
            return perms.roster_room_id && ids.has(perms.roster_room_id) ? perms.roster_room_id : ALL;
        }
        const saved = loadView();
        if (saved && saved !== ALL && ids.has(parseInt(saved, 10))) return parseInt(saved, 10);
        return ALL;
    }
    /** Všechny ordinace: the head of a room column opens that room (Enter / Space too). */
    openRoom(column) {
        if (column.room_id) this.selectView(column.room_id);
    }
    onHeadKey(ev, column) {
        if (column.room_id && (ev.key === "Enter" || ev.key === " ")) {
            ev.preventDefault();
            this.openRoom(column);
        }
    }
    selectView(view) {
        this.state.view = view;
        this.state.showUnassigned = false;
        if (!this.state.data?.perms.member_account) saveView(view);
    }

    // ------------------------------------------------------------ getters
    get columns() { return this.state.data?.columns || []; }
    get unassigned() { return this.columns.find((c) => !c.room_id); }
    get roomColumns() { return this.columns.filter((c) => c.room_id); }
    get currentColumn() {
        return this.state.view === ALL ? null : this.columns.find((c) => c.room_id === this.state.view) || null;
    }
    get canCall() { return !!this.state.data?.perms.can_call; }
    get sections() { return ROOM_SECTIONS; }
    /** Arrived but not assigned (waiting first, longest waiting on top; then in_room without a room). */
    get unassignedArrived() {
        const col = this.unassigned;
        return col ? [...col.sections.waiting, ...col.sections.in_room] : [];
    }
    get unassignedWaiting() { return this.unassigned?.sections.waiting || []; }
    get unassignedText() {
        const n = this.unassignedArrived.length;
        return n + " " + plural(n, "pacient čeká", "pacienti čekají", "pacientů čeká") + " na ordinaci";
    }
    /** Všechny ordinace: the line on top. */
    get summary() {
        let waiting = 0, inRoom = 0;
        for (const col of this.columns) {
            waiting += col.counts.waiting;
            inRoom += col.room_id ? col.counts.in_room : 0;
        }
        return { waiting, inRoom, unassigned: this.unassignedArrived.length };
    }
    onViewChange(ev) {
        const value = ev.target.value;
        this.selectView(value === ALL ? ALL : parseInt(value, 10));
    }
    /** Shift text of the room header: "MVDr. A, 7:00–14:00" once per doctor on duty now. */
    get dutyLine() {
        const column = this.currentColumn;
        if (!column) return null;
        if (this.state.data.is_today && column.on_duty.length) {
            const now = column.shifts.filter((s) => s.now);
            const parts = column.on_duty.map((d) => {
                const shift = now.find((s) => s.doctor === d.name);
                return shift ? d.name + ", " + shift.label : d.name;
            });
            return { now: true, text: parts.join(" a ") };
        }
        return { now: false, text: column.shifts.map((s) => s.doctor + " " + s.label).join(", ") };
    }
    // a WinVet appointment says so instead of "Objednáno" (it is read-only, booked in WinVet)
    tile(it) { return visitTile(it, it.stage, it.source === "winvet" ? { stateText: "z WinVetu" } : {}); }
    /** One primary action by state: Čeká -> Zavolat (nurse, doctor), V ordinaci -> Otevřít kartu. */
    primaryAction(it) {
        if (it.stage === "waiting" && it.record_id && this.canCall) return "call";
        if (it.stage === "in_room" && (it.record_id || it.pet_id)) return "open";
        return null;
    }
    canNote(it) { return !!(it.record_id && it.stage !== "done"); }
    canOpenFromMenu(it) { return !!((it.record_id || it.pet_id) && this.primaryAction(it) !== "open"); }
    /** Task 30: a WinVet appointment without a pet (title only) is paired with a card first. */
    canPair(it) { return !!(it.source === "winvet" && it.winvet_event_id && it.needs_pairing); }
    hasMenu(it) { return this.canOpenFromMenu(it) || this.canNote(it) || this.canPair(it) || !!it.draggable; }

    sectionItems(column, key) { return column.sections[key] || []; }
    /** Všechny ordinace: nobody today (booked, waiting, in the room, done) -> a slim column. */
    isEmptyColumn(column) {
        return ![...ROOM_SECTIONS.map((s) => s.key), "done"].some((key) => this.sectionItems(column, key).length);
    }
    /** Všechny ordinace: grid tracks - slim for nobody today, else at least 360 px sharing the rest. */
    get columnTracks() {
        return this.columns.map((c) => (this.isEmptyColumn(c) ? "140px" : "minmax(360px, 1fr)")).join(" ");
    }
    /** Všechny ordinace: long texts are clamped on the tile, the full text is the tooltip. */
    tileTitle(it) {
        const parts = [it.pet_name, it.owner, it.procedure].filter(Boolean);
        return parts.some((p) => p.length > TILE_TEXT_CLAMP) ? parts.join("\n") : false;
    }
    isDoneOpen(column) { return !!this.state.openDone[column.key]; }
    toggleDone(column) { this.state.openDone[column.key] = !this.state.openDone[column.key]; }

    dutyText(column) {
        if (!column.room_id) return "Čekají na ordinaci";
        if (!this.state.data.is_today) return column.shifts.map((s) => s.doctor + " " + s.label).join(", ") || "Nikdo ve službě";
        return column.on_duty.map((d) => d.name).join(", ") || "Teď nikdo ve službě";
    }
    roomName(roomId) {
        return this.state.data.rooms.find((r) => r.id === roomId)?.name || "Nepřiřazení";
    }

    // ------------------------------------------------------------ drag & drop (Všechny ordinace)
    onDragStart(ev, it) {
        this.state.drag = it.key;
        this.dragItem = it;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", it.key);
    }
    onDragEnd() {
        this.state.drag = null;
        this.state.dropKey = null;
        this.dragItem = null;
    }
    onDragOver(ev, column) {
        if (!this.state.drag) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        if (this.state.dropKey !== column.key) this.state.dropKey = column.key;
    }
    async onDrop(ev, column) {
        ev.preventDefault();
        const it = this.dragItem;
        this.onDragEnd();
        if (!it || (it.room_id || null) === (column.room_id || null)) return;
        await this.assign(it, column.room_id);
    }

    // ------------------------------------------------------------ actions
    async pickRoomFor(it, roomId) {
        if ((it.room_id || null) === (roomId || null)) return;
        await this.assign(it, roomId);
    }
    toggleUnassigned() { this.state.showUnassigned = !this.state.showUnassigned; }
    /** Vzít dalšího: the unassigned patient waiting the longest comes into this room. */
    async takeNext() {
        const column = this.currentColumn;
        if (!column) return;
        const result = await this.run("take_next_patient", [column.room_id]);
        if (result === null) return;
        if (!result) {
            this.notification.add("Na ordinaci už nikdo nečeká.", { type: "info" });
            return;
        }
        this.notification.add(result.pet_name + " → " + column.name, { type: "success" });
        this.askDoctor({ record_id: result.record_id, pet_name: result.pet_name }, column.room_id, result);
    }
    editNote(it) {
        this.dialog.add(RoomNoteDialog, {
            item: it,
            onSave: async (note) => {
                return (await this.run("set_reception_note", [it.record_id, note])) !== null;
            },
        });
    }

    async run(method, args) {
        if (this.state.busy) return null;
        this.state.busy = true;
        try {
            return await this.orm.call(RECEPTION, method, args);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
            return null;
        } finally {
            this.state.busy = false;
            await this.load().catch(() => {});
        }
    }
    askDoctor(it, roomId, result) {
        if (result?.needs_doctor?.length) {
            this.state.pickDoctor = { item: it, roomId, doctors: result.needs_doctor };
        }
    }
    async assign(it, roomId) {
        const result = await this.run("assign_room", [it.record_id, roomId || false]);
        if (result) {
            this.notification.add(result.pet_name + " → " + this.roomName(roomId || null), { type: "success" });
            this.askDoctor(it, roomId, result);
        }
    }
    async callPatient(it, roomId) {
        const result = await this.run("call_patient", [it.record_id, roomId || it.room_id || false]);
        if (result) this.askDoctor(it, roomId || it.room_id, result);
    }
    async chooseDoctor(doctor) {
        const pick = this.state.pickDoctor;
        this.state.pickDoctor = null;
        if (!pick || !doctor) return;
        await this.run("assign_room", [pick.item.record_id, pick.roomId || false, doctor.id]);
    }
    /** Spárovat…: the Kartotéka dialog of the till in the mode `winvet` (same rules, same API). */
    pairWinvet(it) {
        this.dialog.add(CardIndexDialog, {
            mode: "winvet",
            winvet: it,
            onChanged: () => this.load().catch(() => {}),
        });
    }
    /** Same as the rows of "Moji pacienti dnes": the card of the pet on today's record. */
    async openCard(it) {
        try {
            if (it.pet_id) {
                await this.action.doAction({
                    type: "ir.actions.client", tag: "elite_vet_clinic.patient_card",
                    name: "Karta pacienta – " + (it.pet_name || ""),
                    params: { pet_id: it.pet_id, reservation_id: it.reservation_id || false },
                });
                return;
            }
            // web booking without a matched pet: the reservation's own action matches it first
            const action = await this.orm.call("elite.vet.reservation", "action_open_patient_card", [[it.reservation_id]]);
            await this.action.doAction(action);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
        }
    }
}

registry.category("actions").add("elite_vet_reception.room_board", RoomBoard);
