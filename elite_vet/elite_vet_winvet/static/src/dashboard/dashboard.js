/** @odoo-module **/
/**
 * Revenue dashboard over the WinVet data (client action "elite_vet_winvet.dashboard").
 * Figures come from elite.vet.winvet.dashboard.get_data(); charts use Odoo's Chart.js bundle.
 * Every card, bar and row opens the matching records (pivot/list) for details and export.
 */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";

const COLORS = { service: "#2b7870", product: "#ea580c", other: "#94a3b8" };
const PALETTE = ["#2b7870", "#ea580c", "#2563eb", "#db2777", "#7c3aed", "#4d7c0f", "#b45309", "#0891b2", "#64748b"];
const KIND_LABELS = { service: "Úkony", product: "Léky a zboží", other: "Jiné" };

const money = new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "CZK", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 1 });

function pad(n) { return String(n).padStart(2, "0"); }
function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
function parseIso(s) { return new Date(s + "T12:00:00"); }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function startOfWeek(d) { return addDays(d, -((d.getDay() + 6) % 7)); }
function czDate(s) { const d = parseIso(s); return d.getDate() + ". " + (d.getMonth() + 1) + ". " + d.getFullYear(); }

/** Preset periods: [label, () => {from, to, compareFrom, compareTo}] (dates as Date). */
function presets(today) {
    const y = today.getFullYear(), m = today.getMonth();
    const monthStart = new Date(y, m, 1, 12), prevMonthStart = new Date(y, m - 1, 1, 12);
    const prevMonthEnd = new Date(y, m, 0, 12);
    const dayOfMonth = today.getDate();
    const sameDayPrevMonth = new Date(y, m - 1, Math.min(dayOfMonth, prevMonthEnd.getDate()), 12);
    const week = startOfWeek(today);
    return {
        today: { label: "Dnes", from: today, to: today, compareFrom: addDays(today, -7), compareTo: addDays(today, -7) },
        yesterday: { label: "Včera", from: addDays(today, -1), to: addDays(today, -1), compareFrom: addDays(today, -8), compareTo: addDays(today, -8) },
        week: { label: "Tento týden", from: week, to: today, compareFrom: addDays(week, -7), compareTo: addDays(today, -7) },
        last_week: { label: "Minulý týden", from: addDays(week, -7), to: addDays(week, -1) },
        month: { label: "Tento měsíc", from: monthStart, to: today, compareFrom: prevMonthStart, compareTo: sameDayPrevMonth },
        last_month: { label: "Minulý měsíc", from: prevMonthStart, to: prevMonthEnd,
                      compareFrom: new Date(y, m - 2, 1, 12), compareTo: new Date(y, m - 1, 0, 12) },
        year: { label: "Letos", from: new Date(y, 0, 1, 12), to: today, compareFrom: new Date(y - 1, 0, 1, 12), compareTo: new Date(y - 1, m, dayOfMonth, 12) },
        all: { label: "Od začátku", from: null, to: null },
    };
}

export class WinvetDashboard extends Component {
    static template = "elite_vet_winvet.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.today = new Date(); this.today.setHours(12, 0, 0, 0);
        this.presets = presets(this.today);
        this.state = useState({ preset: "month", from: "", to: "", data: null, loading: true });
        this.refs = {
            daily: useRef("daily"), users: useRef("users"), payments: useRef("payments"), species: useRef("species"),
        };
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    // ---------- data ----------
    get presetList() { return Object.entries(this.presets).map(([key, p]) => ({ key, label: p.label })); }

    async load() {
        this.state.loading = true;
        let args = [null, null, null, null, this.state.preset !== "all"];
        if (this.state.preset === "custom") {
            args = [this.state.from || null, this.state.to || null, null, null, true];
        } else {
            const p = this.presets[this.state.preset];
            args = [p.from ? iso(p.from) : null, p.to ? iso(p.to) : null,
                    p.compareFrom ? iso(p.compareFrom) : null, p.compareTo ? iso(p.compareTo) : null,
                    this.state.preset !== "all"];
        }
        const data = await this.orm.call("elite.vet.winvet.dashboard", "get_data", args);
        this.state.data = data;
        this.state.from = data.period.from;
        this.state.to = data.period.to;
        this.state.loading = false;
    }
    async setPreset(key) {
        this.state.preset = key;
        await this.load();
        this.renderCharts();
    }
    async onDateChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.preset = "custom";
        await this.load();
        this.renderCharts();
    }

    // ---------- formatting ----------
    money(v) { return money.format(v || 0); }
    number(v) { return number.format(v || 0); }
    periodLabel(p) { return p.from === p.to ? czDate(p.from) : czDate(p.from) + " – " + czDate(p.to); }
    delta(key) {
        const d = this.state.data;
        if (!d.kpi_previous) return { text: "", cls: "" };
        const now = d.kpi[key] || 0, prev = d.kpi_previous[key] || 0;
        if (!prev) return now ? { text: "nové", cls: "text-success" } : { text: "", cls: "" };
        const ratio = now / prev;
        if (ratio > 10) return { text: "▲ víc než 10×", cls: "text-success" };
        const pct = (ratio - 1) * 100;
        return { text: (pct >= 0 ? "▲ " : "▼ ") + Math.abs(pct).toFixed(0) + " %", cls: pct >= 0 ? "text-success" : "text-danger" };
    }
    get cards() {
        const k = this.state.data.kpi;
        return [
            { key: "revenue", label: "Tržby (položky)", value: this.money(k.revenue), open: () => this.openLines() },
            { key: "services", label: "Úkony", value: this.money(k.services), open: () => this.openLines([["kind", "=", "service"]], "Úkony") },
            { key: "products", label: "Léky a zboží", value: this.money(k.products), open: () => this.openLines([["kind", "=", "product"]], "Léky a zboží") },
            { key: "visits", label: "Návštěvy s účtem", value: this.number(k.visits), open: () => this.openVisits() },
            { key: "avg_per_visit", label: "Průměr na návštěvu", value: this.money(k.avg_per_visit), open: () => this.openLines() },
            { key: "payments", label: "Přijaté platby", value: this.money(k.payments), open: () => this.openPayments() },
        ];
    }
    sharePct(value, total) { return total ? Math.round((value / total) * 100) : 0; }

    // ---------- drill-down ----------
    dateDomain() { return [["date", ">=", this.state.data.period.from], ["date", "<=", this.state.data.period.to]]; }
    openLines(extra = [], title = "Tržby podle položek") {
        this.action.doAction({
            type: "ir.actions.act_window", name: title + " · " + this.periodLabel(this.state.data.period),
            res_model: "elite.vet.sale.line", views: [[false, "pivot"], [false, "graph"], [false, "list"]],
            domain: [...this.dateDomain(), ...extra], context: { pivot_row_groupby: ["item_name"] },
        });
    }
    openPayments(extra = []) {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Platby · " + this.periodLabel(this.state.data.period),
            res_model: "elite.vet.payment", views: [[false, "pivot"], [false, "graph"], [false, "list"]],
            domain: [...this.dateDomain(), ...extra],
        });
    }
    openVisits() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Návštěvy · " + this.periodLabel(this.state.data.period),
            res_model: "elite.vet.visit", views: [[false, "list"], [false, "form"]], domain: this.dateDomain(),
        });
    }
    openItem(row, kind) { this.openLines([["item_name", "=", row.name], ["kind", "=", kind]], row.name); }

    // ---------- charts ----------
    destroyCharts() { this.charts.forEach((c) => c.destroy()); this.charts = []; }
    renderCharts() {
        this.destroyCharts();
        const d = this.state.data;
        if (!d || !window.Chart) return;
        const Chart = window.Chart;
        const moneyTick = (v) => money.format(v);
        const tooltipMoney = { callbacks: { label: (ctx) => (ctx.dataset.label ? ctx.dataset.label + ": " : ctx.label + ": ") + money.format(ctx.parsed.y ?? ctx.parsed.x ?? ctx.parsed) } };

        // revenue over time (per month when the period is long)
        let rows = d.daily, labels;
        if (rows.length > 62) {
            const months = {};
            for (const r of rows) {
                const key = r.date.slice(0, 7);
                months[key] = months[key] || { date: key, service: 0, product: 0, other: 0 };
                for (const k of ["service", "product", "other"]) months[key][k] += r[k];
            }
            rows = Object.values(months);
            labels = rows.map((r) => r.date.slice(5, 7) + "/" + r.date.slice(0, 4));
        } else {
            labels = rows.map((r) => { const x = parseIso(r.date); return x.getDate() + ". " + (x.getMonth() + 1) + "."; });
        }
        if (this.refs.daily.el) {
            this.charts.push(new Chart(this.refs.daily.el, {
                type: "bar",
                data: { labels, datasets: ["service", "product", "other"].map((k) => ({
                    label: KIND_LABELS[k], data: rows.map((r) => r[k]), backgroundColor: COLORS[k], stack: "s" })) },
                options: { maintainAspectRatio: false, plugins: { tooltip: tooltipMoney, legend: { position: "bottom" } },
                           scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: moneyTick } } } },
            }));
        }
        if (this.refs.users.el) {
            const users = d.by_user;
            this.charts.push(new Chart(this.refs.users.el, {
                type: "bar",
                data: { labels: users.map((u) => u.name), datasets: ["service", "product", "other"].map((k) => ({
                    label: KIND_LABELS[k], data: users.map((u) => u[k]), backgroundColor: COLORS[k], stack: "s" })) },
                options: { indexAxis: "y", maintainAspectRatio: false,
                           plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (ctx) => ctx.dataset.label + ": " + money.format(ctx.parsed.x) } } },
                           scales: { x: { stacked: true, ticks: { callback: moneyTick } }, y: { stacked: true } },
                           onClick: (_e, els) => { if (els.length) { const u = users[els[0].index]; this.openLines(u.id ? [["entered_by_id", "=", u.id]] : [["entered_by_id", "=", false]], u.name); } } },
            }));
        }
        const doughnut = (ref, rows, onClick) => {
            if (!ref.el) return;
            this.charts.push(new Chart(ref.el, {
                type: "doughnut",
                data: { labels: rows.map((r) => r.label), datasets: [{ data: rows.map((r) => r.amount), backgroundColor: rows.map((_r, i) => PALETTE[i % PALETTE.length]) }] },
                options: { maintainAspectRatio: false, plugins: { legend: { position: "right" },
                           tooltip: { callbacks: { label: (ctx) => ctx.label + ": " + money.format(ctx.parsed) } } },
                           onClick: (_e, els) => { if (els.length) onClick(rows[els[0].index]); } },
            }));
        };
        doughnut(this.refs.payments, d.payment_methods, (r) => this.openPayments([["method", "=", r.method]]));
        doughnut(this.refs.species, d.species, (r) => this.openLines([["species", "=", r.species]], r.label));
    }
}

registry.category("actions").add("elite_vet_winvet.dashboard", WinvetDashboard);
