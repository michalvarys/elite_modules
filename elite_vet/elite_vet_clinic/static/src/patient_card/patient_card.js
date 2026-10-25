/** @odoo-module **/
// Patient card (client action elite_vet_clinic.patient_card): start screen "Moji pacienti dnes"
// with one search field, and the card itself (history | today's record | bill).
// Backend API: models/patient_card.py (shapes documented in the module README).
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import {
    Component, useState, useRef, onWillStart, onMounted, onPatched, onWillUnmount, useExternalListener,
} from "@odoo/owl";

const MODEL = "elite.vet.clinical.record";
const SAVE_DELAY = 800;          // autosave after the last keystroke
const SEARCH_DELAY = 250;
const STALE_MS = 60000;          // reload the card on window focus when older than this
const NUMBER_FIELDS = ["temperature", "weight", "heart_rate", "respiratory_rate"];
const TEXT_FIELDS = ["anamnesis", "examination", "diagnosis"];
const NUMBER_RE = /^\d+([.,]\d+)?$/;

// ---------------------------------------------------------------- formatting (cs-CZ, fixed)
const NF = {};
function fmtNum(value, maxFrac = 2) {
    if (value === null || value === undefined || value === "") return "";
    NF[maxFrac] = NF[maxFrac] || new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: maxFrac });
    return NF[maxFrac].format(value);
}
function fmtMoney(value) { return fmtNum(value || 0, 2) + " Kč"; }
// Input value: no grouping, decimal comma ("38,5").
function inputNum(value) {
    if (value === null || value === undefined || value === "" || value === false) return "";
    return String(value).replace(".", ",");
}
function fmtDate(iso, today) {
    if (!iso) return "";
    if (today && iso === today) return "dnes";
    const [y, m, d] = iso.split("-").map(Number);
    return d + ". " + m + ". " + y;
}
function nowHHMM() {
    return new Date().toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" });
}
function errorMessage(e) { return e?.data?.message || e?.message || String(e); }
function firstLine(text) { return (text || "").trim().split("\n")[0].trim(); }
// One-line summary of a WinVet note: skips headings ("Anamnéza:") and measurement lines
// ("Čas: 15:22", "Hmotnost: 2,2") and drops a short "Label:" prefix.
const META_LINE = /^(čas|hmotnost|teplota|váha|tep|dech)\s*:/i;
function noteSummary(text) {
    for (let line of (text || "").split("\n")) {
        line = line.trim();
        if (!line || line.endsWith(":") || META_LINE.test(line)) continue;
        line = line.replace(/^[^:\d()]{2,28}:\s+/, "");
        return line;
    }
    return "";
}

// ---------------------------------------------------------------- Picker (popover with search)
// Generic list with a search field: price list items, bundles, text templates.
// `load(term)` returns [{id, title, subtitle, right, raw}]; ↑↓ Enter Esc.
export class Picker extends Component {
    static template = "elite_vet_clinic.Picker";
    static props = {
        load: Function, onPick: Function, onClose: Function,
        placeholder: { type: String, optional: true },
        remote: { type: Boolean, optional: true },
        emptyText: { type: String, optional: true },
        freeLabel: { type: Function, optional: true },   // term -> label of "add outside the list" (or null)
        onFree: { type: Function, optional: true },
        align: { type: String, optional: true },
    };

    setup() {
        this.state = useState({ term: "", items: [], active: 0, loading: true });
        this.rootRef = useRef("root");
        this.inputRef = useRef("input");
        this.seq = 0;
        useExternalListener(window, "mousedown", (ev) => {
            // The anchor (parent) holds the toggle button: a click there toggles instead.
            const anchor = this.rootRef.el?.parentElement;
            if (anchor && !anchor.contains(ev.target)) this.props.onClose();
        });
        onMounted(() => this.inputRef.el?.focus());
        onWillStart(() => this.fetch(""));
        onWillUnmount(() => clearTimeout(this.timer));
    }
    async fetch(term) {
        const seq = ++this.seq;
        this.state.loading = true;
        const items = await this.props.load(term);
        if (seq !== this.seq) return;
        this.state.items = items;
        this.state.active = 0;
        this.state.loading = false;
    }
    onInput(ev) {
        this.state.term = ev.target.value;
        clearTimeout(this.timer);
        if (this.props.remote) {
            this.timer = setTimeout(() => this.fetch(this.state.term), SEARCH_DELAY);
        } else {
            this.fetch(this.state.term);
        }
    }
    get freeText() {
        const term = this.state.term.trim();
        return term && this.props.freeLabel ? this.props.freeLabel(term) : null;
    }
    get optionCount() { return this.state.items.length + (this.freeText ? 1 : 0); }
    onKeydown(ev) {
        const n = this.optionCount;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            if (n) this.state.active = (this.state.active + 1) % n;
            this.scrollActive();
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            if (n) this.state.active = (this.state.active - 1 + n) % n;
            this.scrollActive();
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            this.choose(this.state.active);
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.props.onClose();
        }
    }
    scrollActive() {
        // after render
        setTimeout(() => this.rootRef.el?.querySelector(".evpc-opt-active")?.scrollIntoView({ block: "nearest" }));
    }
    choose(index) {
        if (this.state.loading && this.props.remote) return;
        if (index < this.state.items.length) {
            this.props.onPick(this.state.items[index]);
        } else if (this.freeText && this.props.onFree) {
            this.props.onFree(this.state.term.trim());
        }
    }
}

// ---------------------------------------------------------------- PatientSearch
// One field: pet name, owner name, phone, chip (search_patients).
export class PatientSearch extends Component {
    static template = "elite_vet_clinic.PatientSearch";
    static props = {
        onSelect: Function,
        big: { type: Boolean, optional: true },
        autofocus: { type: Boolean, optional: true },
        today: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ term: "", results: [], active: 0, open: false, loading: false, searched: false });
        this.rootRef = useRef("root");
        this.inputRef = useRef("input");
        this.seq = 0;
        useExternalListener(window, "mousedown", (ev) => {
            if (this.rootRef.el && !this.rootRef.el.contains(ev.target)) this.state.open = false;
        });
        onMounted(() => { if (this.props.autofocus) this.inputRef.el?.focus(); });
        onWillUnmount(() => clearTimeout(this.timer));
    }
    onInput(ev) {
        this.state.term = ev.target.value;
        clearTimeout(this.timer);
        const term = this.state.term.trim();
        if (term.length < 2) {
            this.seq++;
            Object.assign(this.state, { results: [], open: false, loading: false, searched: false });
            return;
        }
        this.state.loading = true;
        this.timer = setTimeout(() => this.search(term), SEARCH_DELAY);
    }
    onFocus() { if (this.state.results.length) this.state.open = true; }
    async search(term) {
        const seq = ++this.seq;
        const results = await this.orm.call(MODEL, "search_patients", [term, 20]);
        if (seq !== this.seq) return;
        Object.assign(this.state, { results, active: 0, open: true, loading: false, searched: true });
    }
    onKeydown(ev) {
        const n = this.state.results.length;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.open = true;
            if (n) this.state.active = (this.state.active + 1) % n;
            this.scrollActive();
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            if (n) this.state.active = (this.state.active - 1 + n) % n;
            this.scrollActive();
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            if (this.state.open && n) this.select(this.state.results[this.state.active]);
        } else if (ev.key === "Escape") {
            if (this.state.open) {
                ev.preventDefault();
                this.state.open = false;
            } else if (this.state.term) {
                ev.preventDefault();
                this.state.term = "";
                Object.assign(this.state, { results: [], searched: false });
            }
        }
    }
    scrollActive() {
        setTimeout(() => this.rootRef.el?.querySelector(".evpc-opt-active")?.scrollIntoView({ block: "nearest" }));
    }
    select(pet) {
        this.state.open = false;
        this.state.term = "";
        this.state.results = [];
        this.state.searched = false;
        this.inputRef.el?.blur();
        this.props.onSelect(pet);
    }
    petMeta(p) { return [p.species_label, p.breed].filter(Boolean).join(", "); }
    fmtDate(iso) { return fmtDate(iso, this.props.today); }
}

// ---------------------------------------------------------------- PatientCard
export class PatientCard extends Component {
    static template = "elite_vet_clinic.PatientCard";
    static components = { Picker, PatientSearch };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.rootRef = useRef("root");
        this.state = useState({
            mode: "start", loading: true,
            today: null,             // my_patients_today()
            data: null,              // card_data()
            record: null,            // RECORD of today
            petId: null, reservationId: null,
            form: this.emptyForm(),
            invalid: {},
            save: { status: "idle", at: null },
            popover: null,           // "service" | "product" | "bundle" | "tpl-<section>"
            tlFilter: "all", expanded: {}, showAll: {},
            busy: false, flashLine: null,
            roomNote: "",            // Poznámka pro recepci (saved on its own, also after Hotovo)
            roomNoteSave: { status: "idle", at: null },
        });
        this.dirty = new Set();
        this.roomNoteDirty = false;
        this.lastLoad = 0;

        // From a button: action.params {pet_id, reservation_id}; after a page reload the pet id
        // comes back from the URL as props.resId (see setUrl).
        const action = this.props.action || {};
        const params = action.params || action.context?.params || {};
        const petId = parseInt(params.pet_id || params.resId || this.props.resId || 0, 10) || null;
        const reservationId = parseInt(params.reservation_id || 0, 10) || null;

        onWillStart(async () => {
            if (petId) {
                await this.openCard(petId, reservationId, { initial: true });
            } else {
                await this.loadToday();
                this.state.loading = false;
            }
        });
        onMounted(() => this.autosizeAll());
        onPatched(() => this.autosizeAll());
        useExternalListener(window, "focus", () => this.onWindowFocus());
        // Leaving the page or the window: write what was typed right away.
        useExternalListener(window, "blur", () => this.flush().catch(() => {}));
        useExternalListener(window, "beforeunload", () => { this.flush().catch(() => {}); });
        onWillUnmount(() => {
            clearTimeout(this.saveTimer);
            clearTimeout(this.roomNoteTimer);
            clearTimeout(this.flashTimer);
            this.flush().catch(() => {});
        });
    }

    emptyForm() {
        return { temperature: "", weight: "", heart_rate: "", respiratory_rate: "",
                 anamnesis: "", examination: "", diagnosis: "" };
    }

    // ------------------------------------------------------------ navigation
    async loadToday() {
        this.state.today = await this.orm.call(MODEL, "my_patients_today", []);
    }
    async goStart() {
        await this.flush();
        this.state.mode = "start";
        this.state.data = null;
        this.state.record = null;
        this.state.petId = null;
        this.state.popover = null;
        this.setUrl(null, "Karta pacienta");
        this.lastLoad = Date.now();
        await this.loadToday();
    }
    async openCard(petId, reservationId = null, { initial = false } = {}) {
        if (!initial) await this.flush();
        Object.assign(this.state, {
            mode: "card", loading: true, petId, reservationId, popover: null,
            tlFilter: "all", expanded: {}, showAll: {}, invalid: {},
            save: { status: "idle", at: null }, roomNoteSave: { status: "idle", at: null },
        });
        this.dirty.clear();
        this.roomNoteDirty = false;
        try {
            await Promise.all([this.loadCard({ openRecord: true }), this.state.today ? null : this.loadToday()]);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
            this.state.mode = "start";
            this.state.data = null;
            if (!this.state.today) await this.loadToday();
        }
        this.state.loading = false;
        if (this.state.data) this.setUrl(petId, "Karta pacienta – " + this.state.data.header.pet.name);
    }
    setUrl(petId, title) {
        // resId lands in the URL (…/action-…/<pet id>), so a page reload reopens the same card.
        this.props.updateActionState?.({ resId: petId || false });
        this.env.config?.setDisplayName?.(title);
    }
    // Rows of "Moji pacienti dnes" and tabs: a web booking without a matched pet goes through
    // the reservation's own action (matches / creates the client and the pet first).
    async openReservation(item) {
        if (item.pet_id) return this.openCard(item.pet_id, item.reservation_id);
        try {
            const action = await this.orm.call("elite.vet.reservation", "action_open_patient_card", [[item.reservation_id]]);
            const p = action.params || {};
            await this.openCard(p.pet_id, p.reservation_id || item.reservation_id);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
        }
    }
    onSearchSelect(pet) { this.openCard(pet.id, null); }

    // ------------------------------------------------------------ loading the card
    async loadCard({ openRecord = false } = {}) {
        const petId = this.state.petId;
        let data = await this.orm.call(MODEL, "card_data", [petId]);
        let record = data.today_record;
        if (openRecord && data.permissions.can_write && !record) {
            // No record yet: show an empty form; the record is created on the first write
            // (ensureRecord), so just looking at a patient leaves nothing behind.
            record = this.placeholderRecord(petId);
        } else if (!openRecord && this.state.record?.id) {
            record = await this.orm.call(MODEL, "get_record", [this.state.record.id]);
        }
        if (petId !== this.state.petId) return;   // another patient was opened meanwhile
        this.state.data = data;
        this.setRecord(record, { replaceForm: true });
        this.lastLoad = Date.now();
    }
    async reloadCard() {
        if (this.state.mode !== "card" || !this.state.petId) return;
        await this.flush();
        try {
            await this.loadCard();
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
        }
    }
    onWindowFocus() {
        if (Date.now() - this.lastLoad < STALE_MS || this.state.popover) return;
        if (this.state.mode === "card") {
            if (this.dirty.size || this.saving) return;
            this.reloadCard();
        } else {
            this.lastLoad = Date.now();
            this.loadToday().catch(() => {});
        }
    }
    placeholderRecord(petId) {
        return {
            id: false, pet_id: petId, doctor_id: null, doctor_name: null, reservation_id: this.state.reservationId || null,
            time: nowHHMM(), state: "draft", state_label: "Rozepsaný", temperature: null, weight: null,
            heart_rate: null, respiratory_rate: null, anamnesis: "", examination: "", diagnosis: "",
            lines: [], amount_total: 0, currency: "Kč", editable: true, placeholder: true,
            reception_note: null, room_note: "", room_note_editable: true,
        };
    }
    /** Id of today's record, creating it on the first write. */
    async ensureRecord() {
        if (this.state.record?.id) return this.state.record.id;
        if (!this.creating) {
            const petId = this.state.petId;
            this.creating = this.orm.call(MODEL, "open_today_record", [petId, this.state.reservationId || false])
                .then(async (rec) => {
                    if (petId === this.state.petId) {
                        this.setRecord(rec);   // the form keeps what is being typed
                        this.orm.call(MODEL, "card_data", [petId]).then((data) => {
                            if (petId === this.state.petId) this.state.data = data;   // timeline shows it
                        }).catch(() => {});
                    }
                    return rec;
                })
                .finally(() => { this.creating = null; });
        }
        return (await this.creating).id;
    }
    setRecord(record, { replaceForm = false } = {}) {
        this.state.record = record;
        if (replaceForm) this.roomNoteDirty = false;
        if (!this.roomNoteDirty) this.state.roomNote = record?.room_note || "";
        if (!record || !replaceForm) return;
        const form = this.emptyForm();
        for (const f of NUMBER_FIELDS) {
            form[f] = this.dirty.has(f) ? this.state.form[f] : inputNum(record[f]);
        }
        for (const f of TEXT_FIELDS) {
            form[f] = this.dirty.has(f) ? this.state.form[f] : record[f] || "";
        }
        this.state.form = form;
    }

    // ------------------------------------------------------------ getters
    get data() { return this.state.data; }
    get pet() { return this.state.data.header.pet; }
    get owner() { return this.state.data.header.owner; }
    get perms() { return this.state.data?.permissions || {}; }
    get isDoctor() { return !!(this.perms.can_edit_templates || this.perms.is_manager); }
    get editable() { return !!this.state.record?.editable; }
    get todayIso() { return this.state.data?.today || this.state.today?.date; }
    fmtDate(iso) { return fmtDate(iso, this.todayIso); }
    fmtNum(v, f) { return fmtNum(v, f); }
    fmtMoney(v) { return fmtMoney(v); }

    get todayItems() { return this.state.today?.items || []; }
    get todaySubtitle() {
        const t = this.state.today;
        if (!t) return "";
        if (t.filtered_by_doctor) return "Rezervace lékařky " + t.doctor.name;
        return "Všechny dnešní rezervace – váš účet není spárovaný s žádnou lékařkou";
    }
    get todayTitleDate() {
        const iso = this.state.today?.date;
        if (!iso) return "";
        const d = new Date(iso + "T12:00:00");
        const days = ["neděle", "pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota"];
        return days[d.getDay()] + " " + fmtDate(iso);
    }
    isCurrentTab(item) {
        return this.state.mode === "card" && item.pet_id && item.pet_id === this.state.petId;
    }
    recordBadge(item) {
        if (item.record_state === "done") return { label: "Hotovo – k pokladně", cls: "evpc-st-done" };
        if (item.record_state === "draft") return { label: "Rozepsaný", cls: "evpc-st-draft" };
        if (item.state === "done") return { label: "Proběhlá", cls: "" };
        return { label: "Bez záznamu", cls: "" };
    }

    // header band
    get petFacts() {
        const p = this.pet;
        return [p.species_label, p.breed, p.sex, p.age_text].filter(Boolean).join(" · ");
    }
    get weightText() {
        const p = this.pet;
        return p.weight ? fmtNum(p.weight, 2) + " kg" : null;
    }
    get weightDelta() {
        const d = this.pet.weight_delta;
        if (d === null || d === undefined || !this.pet.weight) return null;
        if (Math.abs(d) < 0.005) return { text: "beze změny", cls: "" };
        return { text: (d > 0 ? "+" : "−") + fmtNum(Math.abs(d), 2), cls: d > 0 ? "evpc-up" : "evpc-down" };
    }
    get weightTitle() {
        const p = this.pet;
        return p.weight_date ? "Poslední měření " + fmtDate(p.weight_date) + "; změna proti předchozímu měření" : "";
    }
    get ownerPhone() { return this.owner.mobile || this.owner.phone; }
    get vaccinationInfo() {
        const next = this.pet.next_vaccination;
        if (!next) return null;
        return { text: "do " + fmtDate(next), overdue: next < this.todayIso };
    }

    // timeline
    get timeline() {
        const all = this.state.data?.timeline || [];
        const f = this.state.tlFilter;
        if (f === "visits") return all.filter((e) => e.type !== "vaccination");
        if (f === "vacc") return all.filter((e) => e.type === "vaccination");
        return all;
    }
    get tlCounts() {
        const all = this.state.data?.timeline || [];
        const vacc = all.filter((e) => e.type === "vaccination").length;
        return { all: all.length, visits: all.length - vacc, vacc };
    }
    entryKey(e) { return e.type + "-" + e.id; }
    entryIcon(e) {
        return { record: "fa-stethoscope", visit: "fa-archive", vaccination: "fa-eyedropper" }[e.type];
    }
    entryTypeLabel(e) {
        return { record: "Záznam v Odoo", visit: "Návštěva z WinVetu", vaccination: "Očkování" }[e.type];
    }
    entryTitle(e) {
        if (e.type === "vaccination") return e.item || "Očkování";
        if (e.type === "record") {
            if (this.state.record && e.id === this.state.record.id) {
                const f = this.state.form;
                return firstLine(f.diagnosis) || firstLine(f.examination) || firstLine(f.anamnesis) || "Dnešní záznam (zatím bez textu)";
            }
            return e.diagnosis || firstLine(e.summary) || "Záznam bez textu";
        }
        return e.diagnosis || noteSummary(e.notes) || e.case_name || "Návštěva bez textu";
    }
    isOpenRecord(e) { return e.type === "record" && this.state.record && e.id === this.state.record.id; }
    isExpandable(e) { return e.type !== "vaccination" && !this.isOpenRecord(e); }
    toggleEntry(e) {
        if (!this.isExpandable(e)) return;
        const k = this.entryKey(e);
        this.state.expanded[k] = !this.state.expanded[k];
    }
    isLongNotes(text) { return (text || "").length > 700 || (text || "").split("\n").length > 12; }
    toggleShowAll(e) {
        const k = this.entryKey(e);
        this.state.showAll[k] = !this.state.showAll[k];
    }
    recordSections(e) {
        return [
            { key: "anamnesis", label: "Anamnéza", text: e.anamnesis },
            { key: "examination", label: "Vyšetření", text: e.examination },
            { key: "diagnosis", label: "Diagnóza a doporučení", text: e.diagnosis_text },
        ].filter((s) => s.text);
    }

    // today's record
    get sections() {
        return [
            { key: "anamnesis", label: "Anamnéza", placeholder: "Důvod návštěvy, potíže, jak dlouho, co už majitel zkoušel…" },
            { key: "examination", label: "Vyšetření", placeholder: "Celkový stav, sliznice, uzliny, srdce a plíce, břicho…" },
            { key: "diagnosis", label: "Diagnóza a doporučení", placeholder: "Diagnóza, léčba, kontrola za…" },
        ];
    }
    get vitals() {
        return [
            { key: "temperature", label: "Teplota", unit: "°C" },
            { key: "weight", label: "Váha", unit: "kg" },
            { key: "heart_rate", label: "Tep", unit: "/min" },
            { key: "respiratory_rate", label: "Dech", unit: "/min" },
        ];
    }
    get saveText() {
        const s = this.state.save;
        if (s.status === "pending" || s.status === "saving") return "Ukládám…";
        if (s.status === "error") return "Neuloženo";
        if (s.status === "invalid") return "Opravte číslo";
        return s.at ? "Uloženo " + s.at : "Ukládá se samo";
    }
    get canFinish() { return this.editable && !this.state.busy; }

    // ------------------------------------------------------------ visit report (task 27)
    // "Zpráva pro majitele": the PDF of elite_vet_clinic.report_visit_document in a new tab. The
    // record needs some content (a text, a vital value or a bill line); what is typed is saved first.
    get canPrintReport() {
        const f = this.state.form;
        const typed = [...TEXT_FIELDS, ...NUMBER_FIELDS].some((k) => String(f[k] ?? "").trim());
        return !!this.state.record && (typed || this.lines.length > 0);
    }
    isPrintableEntry(e) {
        if (e.type !== "record" || this.isOpenRecord(e)) return false;
        return !!(e.anamnesis || e.examination || e.diagnosis_text || e.vitals_summary || (e.items && e.items.length));
    }
    reportUrl(recordId) {
        return "/report/pdf/elite_vet_clinic.report_visit_document/" + recordId;
    }
    openReport(recordId) {
        window.open(this.reportUrl(recordId), "_blank");
    }
    async printReport() {
        if (!this.canPrintReport || this.state.busy) return;
        // Opened right away (still the click), so the browser does not block it as a popup.
        const tab = window.open("", "_blank");
        try {
            await this.flush();
            const id = this.state.record.id || await this.ensureRecord();
            if (tab) {
                tab.location.href = this.reportUrl(id);
            } else {
                this.openReport(id);
            }
        } catch (e) {
            tab?.close();
            this.notification.add(errorMessage(e), { type: "danger" });
        }
    }
    get lines() { return this.state.record?.lines || []; }

    // ------------------------------------------------------------ autosave
    onField(name, ev) {
        const value = ev.target.value;
        this.state.form[name] = value;
        if (NUMBER_FIELDS.includes(name)) {
            const v = value.trim();
            this.state.invalid[name] = !!v && !NUMBER_RE.test(v);
        }
        if (TEXT_FIELDS.includes(name)) this.autosize(ev.target);
        this.dirty.add(name);
        this.state.save.status = this.hasInvalid ? "invalid" : "pending";
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => this.flush().catch(() => {}), SAVE_DELAY);
    }
    get hasInvalid() { return Object.values(this.state.invalid).some(Boolean); }
    onFieldBlur() { this.flush().catch(() => {}); }
    onVitalKeydown(ev) { if (ev.key === "Enter") { ev.preventDefault(); ev.target.blur(); } }

    // Writes the changed fields (invalid numbers stay unsaved until fixed). Calls are serialised.
    async flush() {
        if (this.roomNoteDirty || this.savingNote) await this.saveRoomNote().catch(() => {});
        clearTimeout(this.saveTimer);
        if (this.saving) {
            await this.saving.catch(() => {});
        }
        if (!this.state.record || !this.state.record.editable || !this.dirty.size) return;
        await this.ensureRecord();
        const record = this.state.record;
        const vals = {};
        for (const name of [...this.dirty]) {
            if (this.state.invalid[name]) continue;
            vals[name] = NUMBER_FIELDS.includes(name) ? this.state.form[name].trim() : this.state.form[name];
            this.dirty.delete(name);
        }
        if (!Object.keys(vals).length) {
            this.state.save.status = "invalid";
            return;
        }
        this.state.save.status = "saving";
        this.saving = this.orm.call(MODEL, "save_record", [record.id, vals]);
        try {
            const result = await this.saving;
            if (this.state.record && this.state.record.id === result.id) {
                this.setRecord(result);   // lines, state; the form keeps what is being typed
            }
            this.state.save = { status: this.dirty.size ? "pending" : this.hasInvalid ? "invalid" : "idle", at: nowHHMM() };
            if (this.dirty.size) {
                this.saveTimer = setTimeout(() => this.flush().catch(() => {}), SAVE_DELAY);
            }
        } catch (e) {
            for (const name of Object.keys(vals)) this.dirty.add(name);
            this.state.save.status = "error";
            this.notification.add("Záznam se nepodařilo uložit: " + errorMessage(e), { type: "danger" });
            throw e;
        } finally {
            this.saving = null;
        }
    }
    retrySave() { this.flush().catch(() => {}); }

    // ------------------------------------------------------------ Poznámka pro recepci
    // Internal note of the room for the reception (request 25. 10.): own call save_room_note,
    // editable also after Hotovo, k pokladně; saved after a pause in typing, on blur and before Hotovo.
    get roomNoteEditable() { return !!this.state.record?.room_note_editable; }
    get roomNoteSaveText() {
        const s = this.state.roomNoteSave;
        if (s.status === "pending" || s.status === "saving") return "Ukládám…";
        if (s.status === "error") return "Neuloženo";
        return s.at ? "Uloženo " + s.at : "";
    }
    onRoomNote(ev) {
        this.state.roomNote = ev.target.value;
        this.roomNoteDirty = true;
        this.state.roomNoteSave.status = "pending";
        clearTimeout(this.roomNoteTimer);
        this.roomNoteTimer = setTimeout(() => this.saveRoomNote().catch(() => {}), SAVE_DELAY);
    }
    async saveRoomNote() {
        clearTimeout(this.roomNoteTimer);
        if (this.savingNote) await this.savingNote.catch(() => {});
        if (!this.roomNoteDirty || !this.state.record || !this.roomNoteEditable) return;
        const id = await this.ensureRecord();
        const text = this.state.roomNote;
        this.roomNoteDirty = false;
        this.state.roomNoteSave.status = "saving";
        this.savingNote = this.orm.call(MODEL, "save_room_note", [id, text]);
        try {
            const rec = await this.savingNote;
            if (this.state.record && this.state.record.id === rec.id) this.state.record.room_note = rec.room_note;
            this.state.roomNoteSave = { status: this.roomNoteDirty ? "pending" : "idle", at: nowHHMM() };
        } catch (e) {
            this.roomNoteDirty = true;
            this.state.roomNoteSave.status = "error";
            this.notification.add("Poznámku pro recepci se nepodařilo uložit: " + errorMessage(e), { type: "danger" });
            throw e;
        } finally {
            this.savingNote = null;
        }
    }

    async onDoctorChange(ev) {
        const doctorId = parseInt(ev.target.value, 10) || false;
        await this.run(async () => {
            await this.flush();
            const rec = await this.orm.call(MODEL, "save_record", [await this.ensureRecord(), { doctor_id: doctorId }]);
            this.setRecord(rec);
            this.state.save = { status: "idle", at: nowHHMM() };
        });
    }

    autosize(el) {
        if (!el) return;
        el.style.height = "auto";
        el.style.height = Math.max(el.scrollHeight + 2, 72) + "px";
    }
    autosizeAll() {
        const root = this.rootRef.el;
        if (!root) return;
        for (const el of root.querySelectorAll("textarea.evpc-text")) {
            if (el.dataset.h !== String(el.value.length)) {
                this.autosize(el);
                el.dataset.h = String(el.value.length);
            }
        }
    }

    // ------------------------------------------------------------ popovers
    togglePopover(name) { this.state.popover = this.state.popover === name ? null : name; }
    closePopover() { this.state.popover = null; }

    templatesFor(section) {
        const t = this.state.data?.templates || {};
        return [...(t[section] || []), ...(t.any || [])];
    }
    loadTemplates(section) {
        return async (term) => {
            const q = term.trim().toLowerCase();
            return this.templatesFor(section)
                .filter((t) => !q || (t.name + " " + t.body + " " + (t.group_name || "")).toLowerCase().includes(q))
                .map((t) => ({ id: t.id, title: t.name, subtitle: (t.body || "").replace(/\s+/g, " ").slice(0, 110), right: t.group_name || "", raw: t }));
        };
    }
    loadBundles() {
        return async (term) => {
            const q = term.trim().toLowerCase();
            return (this.state.data?.bundles || [])
                .filter((b) => !q || (b.name + " " + (b.code || "") + " " + (b.description || "")).toLowerCase().includes(q))
                .map((b) => ({
                    id: b.id, title: b.name,
                    subtitle: [b.code, b.line_count + " " + (b.line_count === 1 ? "položka" : b.line_count < 5 ? "položky" : "položek")].filter(Boolean).join(" · "),
                    right: fmtMoney(b.amount), raw: b,
                }));
        };
    }
    loadItems(kind) {
        return async (term) => {
            const items = await this.orm.call(MODEL, "search_items", [term, kind, 30]);
            return items.map((i) => ({
                id: i.id, title: i.name,
                subtitle: [i.code, i.unit].filter(Boolean).join(" · "),
                right: fmtMoney(i.price), raw: i,
            }));
        };
    }
    freeLabel(term) { return "Přidat mimo ceník: „" + term + "“"; }

    async applyTemplate(section, opt) {
        this.closePopover();
        await this.run(async () => {
            await this.flush();
            const res = await this.orm.call(MODEL, "apply_template", [await this.ensureRecord(), opt.id, section]);
            this.state.form[section] = res.text;
            this.state.record[section] = res.text;
            this.state.save = { status: "idle", at: nowHHMM() };
            // Cursor at the end of the text, ready to continue typing.
            setTimeout(() => {
                const el = this.rootRef.el?.querySelector(`textarea[name="${section}"]`);
                if (el) {
                    this.autosize(el);
                    el.focus();
                    el.setSelectionRange(el.value.length, el.value.length);
                }
            });
        });
    }
    async addBundle(opt) {
        this.closePopover();
        await this.run(async () => {
            const before = new Set(this.lines.map((l) => l.id));
            const rec = await this.orm.call(MODEL, "add_bundle", [await this.ensureRecord(), opt.id]);
            this.setRecord(rec);
            this.flash(rec.lines.filter((l) => !before.has(l.id)).map((l) => l.id));
            this.notification.add("Balíček „" + opt.title + "“ přidán do účtu.", { type: "success" });
        });
    }
    async addItem(opt) {
        this.closePopover();
        await this.run(async () => {
            const rec = await this.orm.call(MODEL, "add_item", [await this.ensureRecord(), opt.id, 1]);
            this.setRecord(rec);
            const line = rec.lines.find((l) => l.item_id === opt.id);
            this.flash(line ? [line.id] : []);
        });
    }
    async addFree(kind, name) {
        this.closePopover();
        await this.run(async () => {
            const before = new Set(this.lines.map((l) => l.id));
            const rec = await this.orm.call(MODEL, "add_free_line", [await this.ensureRecord(), name, 0, 1, kind]);
            this.setRecord(rec);
            const added = rec.lines.filter((l) => !before.has(l.id)).map((l) => l.id);
            this.flash(added);
            // A free line has no price yet: go straight to its price.
            setTimeout(() => this.rootRef.el?.querySelector(`input[data-price-line="${added[0]}"]`)?.focus());
        });
    }
    flash(ids) {
        this.state.flashLine = ids;
        clearTimeout(this.flashTimer);
        this.flashTimer = setTimeout(() => { this.state.flashLine = null; }, 1600);
    }
    isFlash(line) { return (this.state.flashLine || []).includes(line.id); }

    // ------------------------------------------------------------ bill lines
    onLineKeydown(ev) {
        if (ev.key === "Enter") { ev.preventDefault(); ev.target.blur(); }
        if (ev.key === "Escape") { ev.target.value = ev.target.defaultValue; ev.target.blur(); }
    }
    async onLineChange(line, field, ev) {
        const raw = ev.target.value.trim();
        if (!NUMBER_RE.test(raw)) {
            ev.target.value = inputNum(line[field]);
            this.notification.add("„" + raw + "“ není číslo.", { type: "warning" });
            return;
        }
        const value = parseFloat(raw.replace(",", "."));
        if (value === line[field]) return;
        if (field === "quantity" && value === 0) return this.removeLine(line);
        await this.run(async () => {
            const rec = await this.orm.call(MODEL, "update_line", [line.id, { [field]: raw }]);
            this.setRecord(rec);
        });
    }
    async removeLine(line) {
        await this.run(async () => {
            const rec = await this.orm.call(MODEL, "remove_line", [line.id]);
            this.setRecord(rec);
        });
    }
    inputNum(v) { return inputNum(v); }

    // ------------------------------------------------------------ done / reopen
    markDone() {
        if (this.hasInvalid) {
            this.notification.add("Nejdřív opravte vitální hodnoty – některé číslo není platné.", { type: "warning" });
            return;
        }
        const total = fmtMoney(this.state.record.amount_total);
        this.dialog.add(ConfirmationDialog, {
            title: "Uzavřít záznam a poslat účet k pokladně?",
            body: "Záznam " + this.pet.name + " se uzavře a účet " + total + " půjde k pokladně. " +
                  "Upravit ho pak půjde jen po znovuotevření lékařkou." +
                  (this.state.roomNote.trim() ? " Recepce uvidí poznámku: „" + this.state.roomNote.trim() + "“." : ""),
            confirmLabel: "Hotovo, k pokladně",
            cancelLabel: "Pokračovat v záznamu",
            confirm: () => this.run(async () => {
                await this.flush();
                const rec = await this.orm.call(MODEL, "mark_done", [await this.ensureRecord()]);
                this.setRecord(rec, { replaceForm: true });
                this.notification.add("Záznam uzavřen, účet " + total + " je připravený k pokladně.", { type: "success" });
                await this.loadCard();
            }),
            cancel: () => {},
        });
    }
    async reopen() {
        await this.run(async () => {
            const rec = await this.orm.call(MODEL, "reopen_record", [this.state.record.id]);
            this.setRecord(rec, { replaceForm: true });
            await this.loadCard();
        });
    }

    // ------------------------------------------------------------ header actions (dialogs)
    openForm(resModel, resId, name, context = {}) {
        return this.action.doAction({
            type: "ir.actions.act_window", name, res_model: resModel, res_id: resId || false,
            views: [[false, "form"]], target: "new", context,
        }, { onClose: () => this.reloadCard() });
    }
    editPet() { return this.openForm("elite.vet.pet", this.pet.id, "Pacient " + this.pet.name); }
    openOwner() { return this.openForm("res.partner", this.owner.partner_id, "Klient " + this.owner.name); }
    openAlert(alert) {
        return this.openForm("elite.vet.pet.alert", alert.id, "Upozornění", { default_pet_id: this.pet.id });
    }
    addAlert() { return this.openForm("elite.vet.pet.alert", false, "Nové upozornění", { default_pet_id: this.pet.id }); }

    // Back to the screen the card was opened from (e.g. the reservation board): client actions
    // have no control panel, so the bar shows the previous breadcrumb itself.
    get previousCrumb() {
        const crumbs = (this.env.config?.breadcrumbs || []).filter(Boolean);
        const prev = crumbs.length > 1 ? crumbs[crumbs.length - 2] : null;
        return prev && prev.name ? prev : null;
    }
    async goBack() {
        await this.flush().catch(() => {});
        this.previousCrumb?.onSelected?.();
    }

    // Runs a write call; a user error shows as a notification, the card stays as it was.
    async run(fn) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            await fn();
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
            try {
                if (this.state.record?.id) this.setRecord(await this.orm.call(MODEL, "get_record", [this.state.record.id]));
            } catch {
                // keep what is shown
            }
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("elite_vet_clinic.patient_card", PatientCard);
