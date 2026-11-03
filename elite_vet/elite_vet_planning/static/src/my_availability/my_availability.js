/** @odoo-module **/
/**
 * Moje dostupnost (client action elite_vet_planning.my_availability): the logged-in team member
 * marks the days she can work (Můžu / Jen ráno / Jen odpoledne / Nemůžu) and sees her planned
 * shifts. Absences entered by the management are shown locked. Server: elite.vet.planner.my_month.
 */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { hm } from "@elite_vet_planning/planner/planner";

const WEEKDAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];
const MONTHS = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen",
    "září", "říjen", "listopad", "prosinec"];

function pad(n) { return String(n).padStart(2, "0"); }
function shiftMonth(iso, delta) {
    const [y, m] = iso.split("-").map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-01";
}

export class MyAvailability extends Component {
    static template = "elite_vet_planning.MyAvailability";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        const now = new Date();
        // Planning is done ahead: open next month.
        this.state = useState({
            month: shiftMonth(now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-01", 1),
            data: null, busy: false, open: null, note: "",
        });
        onWillStart(() => this.load());
    }

    async call(method, ...args) {
        this.state.busy = true;
        try {
            this.state.data = await this.orm.call("elite.vet.planner", method, [this.state.month, ...args]);
        } finally {
            this.state.busy = false;
        }
    }
    load() { return this.call("my_month"); }
    async goMonth(delta) {
        this.state.month = shiftMonth(this.state.month, delta);
        this.state.open = null;
        await this.load();
    }
    get monthLabel() {
        const [y, m] = this.state.month.split("-").map(Number);
        return MONTHS[m - 1] + " " + y;
    }
    get weekdays() { return WEEKDAYS; }
    get leading() { return Array.from({ length: this.state.data.days[0].weekday }, (_, i) => i); }
    get todayIso() {
        const d = new Date();
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    }
    isPast(day) { return day.date < this.todayIso; }
    req(day) { return this.state.data.requests[day.date]; }
    shifts(day) { return this.state.data.shifts.filter((s) => s.date === day.date); }
    shiftLabel(s) { return `${s.row} ${hm(s.hour_from)}–${hm(s.hour_to)}`; }
    dayClass(day) {
        return ["evm-day", day.weekend ? "evp-we" : "", day.holiday ? "evp-hol" : "",
            this.isPast(day) ? "evm-past" : ""].join(" ");
    }
    openDay(day) {
        const req = this.req(day);
        if (this.isPast(day) || (req && req.locked)) return;
        this.state.open = day;
        this.state.note = req ? req.note : "";
    }
    async pick(code) {
        const day = this.state.open;
        this.state.open = null;
        await this.call("set_my_request", day.date, code, this.state.note);
    }
    async fill(code) { await this.call("fill_my_month", code); }
    fmt(v) { return (Math.round(v * 10) / 10).toLocaleString("cs-CZ"); }
}

registry.category("actions").add("elite_vet_planning.my_availability", MyAvailability);
