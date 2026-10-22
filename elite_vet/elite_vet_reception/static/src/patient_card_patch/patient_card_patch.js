/** @odoo-module **/
// Staged "Moji pacienti dnes" of the patient card (elite_vet_clinic): Čekají (Zavolat),
// V ordinaci, Objednaní – ještě nepřišli, Hotovo dnes. Items come from my_patients_today
// (extended in models/patient_card.py with group, visit_stage, arrived_time, waiting_minutes).
// Ruling R5: opening the card on today's waiting record calls the patient in (once).
import { onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { PatientCard } from "@elite_vet_clinic/patient_card/patient_card";

const RECEPTION = "elite.vet.reception";
const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;

export const PATIENT_GROUPS = [
    { key: "waiting", title: "Čekají", empty: "Nikdo nečeká." },
    { key: "in_room", title: "V ordinaci", empty: "V ordinaci nikdo není." },
    { key: "arriving", title: "Objednaní – ještě nepřišli", empty: "Všichni objednaní už přišli." },
    { key: "done", title: "Hotovo dnes", empty: "Zatím nic hotového." },
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

    stageLine(it) {
        const parts = [];
        if (it.walk_in) parts.push("bez objednání");
        if (it.walk_in && !it.doctor && this.state.today?.filtered_by_doctor) parts.push("kterákoli lékařka");
        if (it.group === "waiting") {
            if (it.arrived_time) parts.push("příchod " + it.arrived_time);
            if (it.waiting_minutes !== null && it.waiting_minutes !== undefined) {
                parts.push("čeká " + it.waiting_minutes + " min");
            }
        } else if (it.group === "in_room") {
            if (it.called_time) parts.push("od " + it.called_time);
            else if (it.arrived_time) parts.push("příchod " + it.arrived_time);
        }
        return parts.join(" · ");
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

    async loadCard() {
        await super.loadCard(...arguments);
        this.callInWaitingRecord();
    },

    /** R5: a nurse or doctor looking at today's waiting record has called the patient in. */
    callInWaitingRecord() {
        const rec = this.state.record;
        if (!rec?.id || rec.visit_stage !== "waiting" || rec.state !== "draft") return;
        if (!this.perms.can_write || rec.date !== this.todayIso || this.calledRecords.has(rec.id)) return;
        this.calledRecords.add(rec.id);
        this.orm.call(RECEPTION, "call_patient", [rec.id]).then(() => {
            if (this.state.record?.id === rec.id) this.state.record.visit_stage = "in_room";
            this.refreshToday();
        }).catch(() => {});   // e.g. the reception role: silently ignored
    },
});
