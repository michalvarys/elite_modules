/** @odoo-module **/
/**
 * Plánování (client action elite_vet_planning.planner): the month plan of the clinic.
 * Tab "Rozpis místností": rows = blocks and their slots, columns = days; a cell holds the
 * shifts planned there (elite.vet.shift). Tab "Požadavky na směny": availability and absences
 * per person and day. Every change goes to the server (elite.vet.planner), which answers
 * with the whole month, so the screen always shows what is stored.
 */
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useRef, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

const { DateTime, Info, Settings } = luxon;

// Quick times of the cell dialog (request: 10–18, 8–14, 9–15, 14–20).
const PRESETS = [[10, 18], [8, 14], [9, 15], [14, 20]];
// Keyboard entry in Požadavky na směny.
const KEY_CODES = { d: "D", n: "NV", l: "L", p: "PN", s: "S", m: "can", r: "morning", o: "afternoon", v: "off" };
// The requests panel above the plan: open / closed and its height, remembered by the browser.
const REQ_OPEN_KEY = "elite_vet_planning.requests_open";
const REQ_HEIGHT_KEY = "elite_vet_planning.requests_height";
const REQ_MIN = 80, REQ_MAX = 1200, REQ_DEFAULT = 260;

function loadSetting(key, fallback) {
    try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : JSON.parse(v);
    } catch {
        return fallback;
    }
}
function saveSetting(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
}

function pad(n) { return String(n).padStart(2, "0"); }
export function monthTitle(iso) { return DateTime.fromISO(iso).toFormat("LLLL yyyy"); }
export function dayTitle(iso) {
    return DateTime.fromISO(iso).toLocaleString({ weekday: "short", day: "numeric", month: "long", year: "numeric" });
}
export function fmtHours(h) { return (Math.round(h * 10) / 10).toLocaleString(Settings.defaultLocale || undefined); }
export function hm(value) {
    let h = Math.floor(value), m = Math.round((value - h) * 60);
    if (m === 60) { h += 1; m = 0; }
    return h + ":" + pad(m);
}
export function parseHm(text) {
    const m = /^\s*(\d{1,2})(?::(\d{2}))?\s*$/.exec(text || "");
    if (!m) return null;
    const v = parseInt(m[1], 10) + (m[2] ? parseInt(m[2], 10) / 60 : 0);
    return v >= 0 && v <= 24 ? v : null;
}
export function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return "#fff";
    const n = parseInt(m[1], 16);
    const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.62 ? "#1e293b" : "#fff";
}
function shiftMonth(iso, delta) {
    const [y, m] = iso.split("-").map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-01";
}
function currentMonth() {
    const d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-01";
}

export class Planner extends Component {
    static template = "elite_vet_planning.Planner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            month: currentMonth(),
            data: null, busy: false,
            cell: null,          // {slot, row, day} of the open cell dialog
            newFrom: "", newTo: "", helperName: "",
            picker: null,        // {member, day, note} of the request picker
            focus: null,         // "memberId|date" of the focused request cell
            reqOpen: loadSetting(REQ_OPEN_KEY, true),
            reqHeight: loadSetting(REQ_HEIGHT_KEY, REQ_DEFAULT),
        });
        this.gridScroll = useRef("gridScroll");
        this.reqScroll = useRef("reqScroll");
        this.onKey = (ev) => {
            if (ev.key === "Escape") { this.state.cell = null; this.state.picker = null; }
        };
        onWillStart(() => this.load());
        onMounted(() => window.addEventListener("keydown", this.onKey));
        onWillUnmount(() => window.removeEventListener("keydown", this.onKey));
    }

    // ---------- data ----------
    async call(method, ...args) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const data = await this.orm.call("elite.vet.planner", method, [this.state.month, ...args]);
            if (data && typeof data === "object" && data.days) {
                this.state.data = data;
                if (data.message) this.notification.add(data.message, { type: "info" });
            }
            return data;
        } finally {
            this.state.busy = false;
        }
    }
    load() { return this.call("load_month"); }
    async goMonth(delta) {
        this.state.month = shiftMonth(this.state.month, delta);
        this.state.cell = null;
        await this.load();
    }

    get monthLabel() {
        return monthTitle(this.state.month);
    }
    get days() { return this.state.data.days; }
    get staffById() {
        const out = {};
        for (const s of this.state.data.staff) out[s.id] = s;
        return out;
    }
    get staffGroups() {
        const data = this.state.data;
        return data.roles.map((r) => ({ ...r, staff: data.staff.filter((s) => s.role === r.key) }))
            .filter((g) => g.staff.length);
    }
    weekdayAbbr(day) { return Info.weekdays("short")[day.weekday]; }
    dayTitle(day) { return dayTitle(day.date); }
    hm(v) { return hm(v); }
    fmt(v) { return fmtHours(v); }
    textOn(hex) { return textOn(hex); }

    dayClass(day, extra = "") {
        return [extra, day.weekend ? "evp-we" : "", day.holiday ? "evp-hol" : "", day.today ? "evp-today" : ""].join(" ");
    }
    slotApplies(slot, day) {
        return slot.days === "all" || (slot.days === "weekend") === day.weekend;
    }
    cellShifts(slot, day) {
        return this.state.data.shifts.filter((s) => s.slot_id === slot.id && s.date === day.date);
    }
    chipLabel(shift) {
        if (!shift.member_id) return shift.helper_name;
        return (this.staffById[shift.member_id] || {}).initials || "?";
    }
    chipStyle(shift) {
        const color = (shift.member_id && (this.staffById[shift.member_id] || {}).color) || "#94a3b8";
        return `background:${color};color:${textOn(color)}`;
    }
    chipTime(shift, slot) {
        return shift.hour_from !== slot.hour_from || shift.hour_to !== slot.hour_to
            ? hm(shift.hour_from) + "–" + hm(shift.hour_to) : "";
    }
    request(memberId, date) {
        return this.state.data.requests.find((r) => r.member_id === memberId && r.date === date);
    }
    /** Warning on a chip: the person has an absence or said "Nemůžu" that day. */
    chipConflict(shift) {
        if (!shift.member_id) return "";
        const req = this.request(shift.member_id, shift.date);
        if (!req) return "";
        if (req.code === "off") return _t("Entered Cannot work for this day");
        if (["D", "NV", "L", "PN", "S"].includes(req.code)) return _t("Has absence %s on this day", req.short);
        if (req.code === "morning" && shift.hour_from >= 12) return _t("Can work in the morning only");
        if (req.code === "afternoon" && shift.hour_from < 12) return _t("Can work in the afternoon only");
        return "";
    }
    absencesOn(day) {
        return this.state.data.requests.filter((r) => r.date === day.date && ["D", "NV", "L", "PN", "S"].includes(r.code)
            && this.staffById[r.member_id]);
    }

    // ---------- cell dialog ----------
    openCell(row, slot, day) {
        if (row.kind === "roster") return;   // read-only row of shifts no block fits
        this.state.cell = { row, slot, day };
        this.state.newFrom = hm(slot.hour_from);
        this.state.newTo = hm(slot.hour_to);
        this.state.helperName = "";
    }
    closeCell() { this.state.cell = null; }
    get presets() { return PRESETS; }
    shiftName(shift) {
        return shift.member_id ? (this.staffById[shift.member_id] || {}).name : shift.helper_name;
    }
    onHelperKey(ev) {
        if (ev.key === "Enter") this.addHelper();
    }
    get cellTitle() {
        const { row, slot, day } = this.state.cell;
        return `${row.name} · ${slot.name} · ${dayTitle(day.date)}`;
    }
    get openShifts() {
        const c = this.state.cell;
        return c ? this.cellShifts(c.slot, c.day) : [];
    }
    pickerGroups() {
        const preferred = this.state.cell.row.preferred_roles;
        return [...this.staffGroups].sort((a, b) => {
            const ia = preferred.indexOf(a.key), ib = preferred.indexOf(b.key);
            return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
        });
    }
    /** What is known about the person on the open day: availability / absence / other shifts. */
    memberHint(member) {
        const day = this.state.cell.day;
        const bits = [];
        const req = this.request(member.id, day.date);
        if (req) bits.push(req.short === "✓" ? _t("can work") : req.short);
        const data = this.state.data;
        for (const s of data.shifts.filter((x) => x.member_id === member.id && x.date === day.date)) {
            const row = data.rows.find((r) => r.id === s.row_id);
            const slot = row?.slots.find((x) => x.id === s.slot_id);
            bits.push(s.assignment ? `Rozpis lékařů ${s.room}` : `${row?.name || ""} ${slot?.name || ""}`.trim());
        }
        return bits.join(" · ");
    }
    memberState(member) {
        const req = this.request(member.id, this.state.cell.day.date);
        if (!req) return "";
        if (["D", "NV", "L", "PN", "S", "off"].includes(req.code)) return "evp-pick-no";
        return "evp-pick-yes";
    }
    setPreset(from, to) {
        this.state.newFrom = hm(from);
        this.state.newTo = hm(to);
    }
    newTimes() {
        const from = parseHm(this.state.newFrom), to = parseHm(this.state.newTo);
        if (from === null || to === null) {
            this.notification.add(_t("Enter the time as 8:00 or 14:30."), { type: "warning" });
            return null;
        }
        return [from, to];
    }
    async addMember(member) {
        const times = this.newTimes();
        if (!times) return;
        const { slot, day } = this.state.cell;
        await this.call("add_shift", slot.id, day.date, member.id, false, times[0], times[1]);
    }
    async addHelper() {
        const times = this.newTimes();
        const name = this.state.helperName.trim();
        if (!times || !name) return;
        const { slot, day } = this.state.cell;
        await this.call("add_shift", slot.id, day.date, false, name, times[0], times[1]);
        this.state.helperName = "";
    }
    async removeShift(shift, ev) {
        ev?.stopPropagation();
        await this.call("remove_shift", shift.id);
    }
    async changeTime(shift, field, ev) {
        const value = parseHm(ev.target.value);
        if (value === null) {
            ev.target.value = hm(shift[field]);
            return;
        }
        const from = field === "hour_from" ? value : shift.hour_from;
        const to = field === "hour_to" ? value : shift.hour_to;
        await this.call("update_shift", shift.id, from, to);
    }
    get assignmentCount() { return this.state.data.shifts.filter((s) => s.assignment).length; }
    async adoptAssignments() { await this.call("adopt_assignments"); }
    notBooked(shift) { return Boolean(shift.booking && shift.booking.ok === false); }
    chipTitle(shift) {
        const conflict = this.chipConflict(shift);
        const origin = shift.assignment ? _t("Service entered in Rezervace › Rozpis lékařů")
            : shift.from_roster ? _t("Shift entered in the roster") : "";
        const booking = shift.booking && shift.booking.ok === false ? shift.booking.text : "";
        return [origin, conflict, booking].filter(Boolean).join(" · ") || null;
    }
    async copyWeek(day, ev) {
        ev.stopPropagation();
        await this.call("copy_previous_week", day.date);
    }

    // ---------- requests panel above the plan ----------
    toggleRequests() {
        this.state.reqOpen = !this.state.reqOpen;
        saveSetting(REQ_OPEN_KEY, this.state.reqOpen);
    }
    startResize(ev) {
        ev.preventDefault();
        const startY = ev.clientY, startH = this.state.reqHeight;
        const move = (e) => {
            this.state.reqHeight = Math.max(REQ_MIN, Math.min(REQ_MAX, startH + e.clientY - startY));
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            saveSetting(REQ_HEIGHT_KEY, this.state.reqHeight);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }
    // Both tables have the same day columns: scrolling one sideways scrolls the other.
    onReqScroll() { this.syncScroll(this.reqScroll.el, this.gridScroll.el); }
    onGridScroll() { this.syncScroll(this.gridScroll.el, this.reqScroll.el); }
    syncScroll(from, to) {
        if (from && to && to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft;
    }

    // ---------- requests ----------
    requestCellKey(member, day) { return member.id + "|" + day.date; }
    openPicker(member, day) {
        const req = this.request(member.id, day.date);
        this.state.focus = this.requestCellKey(member, day);
        this.state.picker = { member, day, note: req?.note || "" };
    }
    async pickCode(code) {
        const { member, day, note } = this.state.picker;
        this.state.picker = null;
        await this.call("set_request", member.id, day.date, code, note);
    }
    async saveNoteOnly() {
        const { member, day, note } = this.state.picker;
        const req = this.request(member.id, day.date);
        this.state.picker = null;
        if (req) await this.call("set_request", member.id, day.date, req.code, note);
    }
    async onRequestKey(member, day, ev) {
        const key = ev.key.toLowerCase();
        const days = this.days, staff = this.state.data.staff;
        const di = days.findIndex((d) => d.date === day.date), si = staff.findIndex((s) => s.id === member.id);
        const move = { arrowright: [0, 1], arrowleft: [0, -1], arrowdown: [1, 0], arrowup: [-1, 0] }[key];
        if (move) {
            ev.preventDefault();
            const s = staff[si + move[0]], d = days[di + move[1]];
            if (s && d) {
                this.state.focus = s.id + "|" + d.date;
                document.querySelector(`[data-req="${this.state.focus}"]`)?.focus();
            }
            return;
        }
        if (key === "enter") { this.openPicker(member, day); return; }
        let code;
        if (key === "delete" || key === "backspace") code = false;
        else if (KEY_CODES[key]) code = KEY_CODES[key];
        else return;
        ev.preventDefault();
        await this.call("set_request", member.id, day.date, code, null);
        document.querySelector(`[data-req="${member.id}|${day.date}"]`)?.focus();
    }
    requestClass(member, day) {
        const req = this.request(member.id, day.date);
        return this.dayClass(day, "evp-req" + (req ? " evp-code-" + req.code : ""));
    }
    countCode(member, code) {
        return this.state.data.requests.filter((r) => r.member_id === member.id && r.code === code).length;
    }
    monthNote(member) { return this.state.data.notes[member.id] || ""; }
    async saveMonthNote(member, ev) {
        await this.orm.call("elite.vet.planner", "set_month_note", [this.state.month, member.id, ev.target.value]);
        this.state.data.notes[member.id] = ev.target.value;
    }
    async moveMember(member, direction) { await this.call("move_member", member.id, direction); }

    // ---------- balance ----------
    balance(member) { return this.state.data.balance[member.id] || this.state.data.balance[String(member.id)]; }
    workedTitle(b) {
        return _t("Shifts %(shifts)s h + D/L/Š %(credited)s h", { shifts: fmtHours(b.shift_hours), credited: fmtHours(b.credited) });
    }
    absenceText(member) {
        const b = this.balance(member);
        return Object.entries(b.absences).filter(([, n]) => n).map(([code, n]) => {
            const c = this.state.data.codes.find((x) => x.key === code);
            return `${c ? c.short : code} ${n}`;
        }).join(", ");
    }

    // ---------- other ----------
    openStaff() { this.action.doAction("elite_vet_planning.action_staff"); }
    print() { window.print(); }
    exportCsv() {
        const data = this.state.data;
        const q = (v) => '"' + String(v ?? "").replace(/"/g, '""') + '"';
        const lines = [];
        lines.push([_t("Shift roster") + " " + this.monthLabel, ...data.days.map((d) => `${d.day}. ${this.weekdayAbbr(d)}`)].map(q).join(";"));
        for (const row of data.rows) {
            for (const slot of row.slots) {
                const cells = data.days.map((d) => this.cellShifts(slot, d).map((s) => {
                    const t = this.chipTime(s, slot);
                    return this.chipLabel(s) + (t ? " " + t : "");
                }).join(" + "));
                lines.push([`${row.name} – ${slot.name} ${slot.time}`, ...cells].map(q).join(";"));
            }
        }
        lines.push(["Absence", ...data.days.map((d) => this.absencesOn(d).map((r) => `${this.staffById[r.member_id].initials} ${r.short}`).join(", "))].map(q).join(";"));
        lines.push("");
        lines.push([_t("Full name"), _t("Initials"), _t("Contract (h/week)"), _t("Fund (h)"), _t("Worked (h)"), _t("Morning"), _t("Afternoon"),
            _t("Full day (12 h)"), _t("Weekends"), _t("Weekends (h)"), "Absence", _t("Balance (h)")].map(q).join(";"));
        for (const m of data.staff) {
            const b = this.balance(m);
            lines.push([m.name, m.initials, fmtHours(m.weekly_hours), fmtHours(b.fond), fmtHours(b.worked), b.morning,
                b.afternoon, b.full_day, b.weekend, fmtHours(b.weekend_hours), this.absenceText(m), fmtHours(b.saldo)].map(q).join(";"));
        }
        lines.push("");
        lines.push([_t("Requests"), ...data.days.map((d) => d.day)].map(q).join(";"));
        for (const m of data.staff) {
            lines.push([m.name, ...data.days.map((d) => this.request(m.id, d.date)?.short || "")].map(q).join(";"));
        }
        // BOM: Excel then reads the file as UTF-8 (Czech diacritics).
        const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `rozpis-sluzeb-${this.state.month.slice(0, 7)}.csv`;
        link.click();
        URL.revokeObjectURL(link.href);
    }
}

registry.category("actions").add("elite_vet_planning.planner", Planner);
