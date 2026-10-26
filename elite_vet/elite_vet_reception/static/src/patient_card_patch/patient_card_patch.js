/** @odoo-module **/
// Staged "Moji pacienti dnes" of the patient card (elite_vet_clinic): Dnes jsou objednaní
// (ještě nepřišli), Čekají (Zavolat), V ordinaci, Hotovo dnes; narrow screens: Čekají first. Items come from my_patients_today
// (extended in models/patient_card.py with group, visit_stage, arrived_time, waiting_minutes).
// Ruling R5: opening the card on today's waiting record calls the patient in (once).
import { onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { PatientCard } from "@elite_vet_clinic/patient_card/patient_card";
import { visitTile } from "@elite_vet_clinic/clinic_ui/clinic_ui";

const RECEPTION = "elite.vet.reception";
const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;

// Task 26: the same names, order and state colours as the screen Ordinace.
export const PATIENT_GROUPS = [
    { key: "arriving", state: "booked", title: "Dnes jsou objednaní", hint: "ještě nepřišli",
      empty: "Všichni objednaní už přišli." },
    { key: "waiting", state: "waiting", title: "Čekají", empty: "Nikdo nečeká." },
    { key: "in_room", state: "in_room", title: "V ordinaci", empty: "V ordinaci nikdo není." },
    { key: "done", state: "done", title: "Hotovo dnes", empty: "Zatím nic hotového." },
];

function errorMessage(e) { return e?.data?.message || e?.message || String(e); }

patch(PatientCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.calledRecords = new Set();   // R5: call_patient at most once per record
        this.callState = useState({ key: null });   // row whose Zavolat is in flight
        this.busService = useService("bus_service");
        this.onReceptionChange = () => this.refreshToday();
        this.busService.subscribe(BUS_MESSAGE, this.onReceptionChange);
        this.busService.start();
        // fallback when the websocket is down: poll while the start screen is visible
        this.todayTimer = setInterval(() => {
            if (this.state.mode === "start" && !document.hidden) this.refreshToday();
        }, POLL_MS);
        onWillUnmount(() => {
            clearInterval(this.todayTimer);
            this.busService.unsubscribe(BUS_MESSAGE, this.onReceptionChange);
        });
    },

    refreshToday() {
        this.loadToday().catch(() => {});
    },

    /** R17: walk-ins without a doctor, offered to every doctor (only in a filtered list). */
    get unassignedItems() { return this.state.today?.unassigned || []; },

    get todaySubtitle() {
        const t = this.state.today;
        if (!t) return "";
        if (t.filtered_by_doctor) return "Pacienti na dnešek – " + t.doctor.name + " (objednaní i neobjednaní)";
        return "Všichni pacienti na dnešek – váš účet není spárovaný s žádnou lékařkou";
    },

    get todayGroups() {
        const items = [...this.todayItems, ...this.unassignedItems];
        return PATIENT_GROUPS.map((g) => {
            let list = items.filter((it) => (it.group || "arriving") === g.key);
            if (g.key === "waiting" || g.key === "in_room") {
                list = [...list].sort((a, b) => (a.arrived_time || "99").localeCompare(b.arrived_time || "99"));
            }
            return { ...g, items: list };
        });
    },

    /** The shared visit tile (clinic_ui) of a row; the room is shown, the doctor only when the
     *  list is not filtered to one doctor (or for a walk-in any doctor may take). */
    patientTile(it, group) {
        const filtered = this.state.today?.filtered_by_doctor;
        let stateText;
        if (group.key === "arriving" || group.key === "done") stateText = this.recordBadge(it).label;
        let doctor = filtered ? null : it.doctor;
        if (it.walk_in && !it.doctor && filtered) doctor = "Kterákoli lékařka";
        return visitTile(it, group.state, { stateText, doctor, room: it.room, roomColor: it.room_color });
    },

    async callPatient(it) {
        if (this.callState.key) return;
        this.callState.key = it.key;
        try {
            await this.orm.call(RECEPTION, "call_patient", [it.record_id]);
            this.calledRecords.add(it.record_id);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
            this.refreshToday();
            return;
        } finally {
            this.callState.key = null;
        }
        await this.loadToday().catch(() => {});
        await this.openReservation(it);
    },

});
