/** @odoo-module **/
// Screen Ordinace (task 15, client action elite_vet_reception.room_board): the visits of the day
// by consultation room. Top switch Všechny ordinace | <room> …:
// - Všechny ordinace: columns Nepřiřazení + one per room; arrived patients are dragged between
//   columns (or "Do ordinace…" on touch screens).
// - one room: its list (V ordinaci, Čekají, Objednaní, Hotovo) with Zavolat / Otevřít kartu and
//   above it the unassigned patients with "Vzít do této ordinace".
// Data: elite.vet.reception.room_board (models/room_board.py, shapes in README.md).
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

const RECEPTION = "elite.vet.reception";
const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;
const VIEW_KEY = "elite_vet_reception.room_view";   // remembered choice of this browser
const ALL = "all";

export const ROOM_SECTIONS = [
    { key: "in_room", title: "V ordinaci", empty: "V ordinaci nikdo není." },
    { key: "waiting", title: "Čekají", empty: "Nikdo nečeká." },
    { key: "booked", title: "Objednaní", empty: "Nikdo další objednaný." },
    { key: "done", title: "Hotovo", empty: "Zatím nic hotového.", collapsed: true },
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

export class RoomBoard extends Component {
    static template = "elite_vet_reception.RoomBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            data: null, loading: true, view: ALL, busy: false,
            drag: null,          // key of the dragged card
            dropKey: null,       // column under the dragged card
            pickRoom: null,      // card whose "Do ordinace…" picker is open
            pickDoctor: null,    // {item, roomId, doctors}: two doctors on duty, who takes it
            openDone: {},        // column key -> Hotovo expanded
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
    selectView(view) {
        this.state.view = view;
        this.state.pickRoom = null;
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
    /** Arrived but not assigned (waiting / in_room without a room). */
    get unassignedArrived() {
        const col = this.unassigned;
        return col ? [...col.sections.in_room, ...col.sections.waiting] : [];
    }

    sectionItems(column, key) { return column.sections[key] || []; }
    isDoneOpen(column) { return !!this.state.openDone[column.key]; }
    toggleDone(column) { this.state.openDone[column.key] = !this.state.openDone[column.key]; }

    stageText(it) {
        if (it.stage === "waiting") {
            return it.waiting_minutes !== null && it.waiting_minutes !== undefined
                ? "Čeká " + it.waiting_minutes + " min" : "Čeká";
        }
        if (it.stage === "in_room") return it.called_time ? "V ordinaci od " + it.called_time : "V ordinaci";
        if (it.stage === "done") return "Hotovo";
        return "Objednáno";
    }
    timeText(it) {
        if (it.arrived_time) {
            return it.reservation_time && it.reservation_time !== it.arrived_time
                ? it.arrived_time + " (obj. " + it.reservation_time + ")" : it.arrived_time;
        }
        return it.time || "–";
    }
    dutyText(column) {
        if (!column.room_id) return "čekají na ordinaci";
        if (!this.state.data.is_today) return column.shifts.map((s) => s.doctor + " " + s.label).join(", ") || "nikdo ve službě";
        return column.on_duty.map((d) => d.name).join(", ") || "nikdo ve službě";
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
    openRoomPicker(it) { this.state.pickRoom = this.state.pickRoom?.key === it.key ? null : it; }
    closePickers() {
        this.state.pickRoom = null;
        this.state.pickDoctor = null;
    }
    async pickRoomFor(it, roomId) {
        this.state.pickRoom = null;
        if ((it.room_id || null) === (roomId || null)) return;
        await this.assign(it, roomId);
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
