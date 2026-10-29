/** @odoo-module **/
/**
 * Přehled herny (client action "elite_arena_ggleap.dashboard").
 * Figures come from elite.arena.ggleap.dashboard.get_data(); charts use Odoo's Chart.js bundle.
 * The page starts with one plain sentence about the period, then cards (with the change
 * against the comparison period), then panels. Every card, bar and row opens the records.
 */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";

const COLORS = { time: "#4f46e5", food: "#ea580c", other: "#94a3b8", visits: "#0f172a" };
const PALETTE = ["#4f46e5", "#ea580c", "#0891b2", "#db2777", "#4d7c0f", "#64748b"];
const KIND_LABELS = { time: "Hraní", food: "Občerstvení", other: "Ostatní", free: "Hraní zdarma" };
const DAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];
const DAY_NAMES = ["v pondělí", "v úterý", "ve středu", "ve čtvrtek", "v pátek", "v sobotu", "v neděli"];
const SEGMENT_COLORS = {
    aktivni_stali: "#16a34a", jednou_nedavno: "#0891b2", ohrozeni: "#d97706",
    ztraceni: "#dc2626", jednou_davno: "#9ca3af", nikdy: "#cbd5e1",
};

const money = new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "CZK", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 0 });

function pad(n) { return String(n).padStart(2, "0"); }
function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
function parseIso(s) { return new Date(s + "T12:00:00"); }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function startOfWeek(d) { return addDays(d, -((d.getDay() + 6) % 7)); }
function czDate(s) { const d = parseIso(s); return d.getDate() + ". " + (d.getMonth() + 1) + ". " + d.getFullYear(); }
/** Czech plural: 1 návštěva, 2–4 návštěvy, 5+ návštěv. */
function plural(n, one, few, many) {
    const v = Math.round(n);
    return whole.format(v) + " " + (v === 1 ? one : v >= 2 && v <= 4 ? few : many);
}

function presets(today) {
    const y = today.getFullYear(), m = today.getMonth();
    const monthStart = new Date(y, m, 1, 12), prevMonthStart = new Date(y, m - 1, 1, 12);
    const prevMonthEnd = new Date(y, m, 0, 12);
    const dayOfMonth = today.getDate();
    const sameDayPrevMonth = new Date(y, m - 1, Math.min(dayOfMonth, prevMonthEnd.getDate()), 12);
    const week = startOfWeek(today);
    return {
        today: { label: "Dnes", from: today, to: today, compareFrom: addDays(today, -7), compareTo: addDays(today, -7), word: "dnes" },
        yesterday: { label: "Včera", from: addDays(today, -1), to: addDays(today, -1), compareFrom: addDays(today, -8), compareTo: addDays(today, -8), word: "včera" },
        week: { label: "Tento týden", from: week, to: today, compareFrom: addDays(week, -7), compareTo: addDays(today, -7), word: "tento týden" },
        last_week: { label: "Minulý týden", from: addDays(week, -7), to: addDays(week, -1), word: "minulý týden" },
        month: { label: "Tento měsíc", from: monthStart, to: today, compareFrom: prevMonthStart, compareTo: sameDayPrevMonth, word: "tento měsíc" },
        last_month: { label: "Minulý měsíc", from: prevMonthStart, to: prevMonthEnd,
                      compareFrom: new Date(y, m - 2, 1, 12), compareTo: new Date(y, m - 1, 0, 12), word: "minulý měsíc" },
        days30: { label: "30 dní", from: addDays(today, -29), to: today, word: "za posledních 30 dní" },
        year: { label: "Letos", from: new Date(y, 0, 1, 12), to: today, compareFrom: new Date(y - 1, 0, 1, 12), compareTo: new Date(y - 1, m, dayOfMonth, 12), word: "letos" },
        all: { label: "Od začátku", from: null, to: null, word: "od začátku" },
    };
}

export class GgleapDashboard extends Component {
    static template = "elite_arena_ggleap.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.today = new Date(); this.today.setHours(12, 0, 0, 0);
        this.presets = presets(this.today);
        this.state = useState({ preset: "month", from: "", to: "", data: null, loading: true });
        this.refs = { daily: useRef("daily"), payments: useRef("payments"), machines: useRef("machines") };
        this.charts = [];
        this.chartsDirty = true;
        const drawIfDirty = () => { if (this.chartsDirty && !this.state.loading) { this.chartsDirty = false; this.renderCharts(); } };
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(drawIfDirty);
        onPatched(drawIfDirty);
        onWillUnmount(() => this.destroyCharts());
    }

    // ---------- data ----------
    get presetList() { return Object.entries(this.presets).map(([key, p]) => ({ key, label: p.label })); }

    async load() {
        this.state.loading = true;
        let args;
        if (this.state.preset === "custom") {
            args = [this.state.from || null, this.state.to || null, null, null, true];
        } else {
            const p = this.presets[this.state.preset];
            args = [p.from ? iso(p.from) : null, p.to ? iso(p.to) : null,
                    p.compareFrom ? iso(p.compareFrom) : null, p.compareTo ? iso(p.compareTo) : null,
                    this.state.preset !== "all"];
        }
        const data = await this.orm.call("elite.arena.ggleap.dashboard", "get_data", args);
        this.chartsDirty = true;
        this.state.data = data;
        this.state.from = data.period.from;
        this.state.to = data.period.to;
        this.state.loading = false;
    }
    async setPreset(key) { this.state.preset = key; await this.load(); }
    async onDateChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.preset = "custom";
        await this.load();
    }

    // ---------- formatting ----------
    money(v) { return money.format(v || 0); }
    number(v) { return number.format(v || 0); }
    whole(v) { return whole.format(v || 0); }
    periodLabel(p) { return p.from === p.to ? czDate(p.from) : czDate(p.from) + " – " + czDate(p.to); }
    syncLabel() {
        const s = this.state.data.sync;
        if (!s.last_success_at) return "data z ggLeapu zatím nejsou";
        const at = new Date(s.last_success_at.replace(" ", "T") + "Z");
        const minutes = Math.round((Date.now() - at.getTime()) / 60000);
        if (minutes < 2) return "data z ggLeapu aktuální";
        if (minutes < 120) return "data z ggLeapu před " + minutes + " min";
        return "data z ggLeapu z " + at.toLocaleString("cs-CZ", { dateStyle: "short", timeStyle: "short" });
    }
    get periodWord() {
        const p = this.presets[this.state.preset];
        return p ? p.word : "v období " + this.periodLabel(this.state.data.period);
    }
    /** One plain sentence: what happened in the period. */
    get headline() {
        const k = this.state.data.kpi;
        if (!k.visits && !k.revenue) return "V tomto období nejsou žádné návštěvy ani prodeje.";
        const word = this.periodWord;
        let text = word.charAt(0).toUpperCase() + word.slice(1) + " k nám přišlo " + plural(k.visits, "návštěva", "návštěvy", "návštěv");
        if (k.players) text += " od " + plural(k.players, "hráče", "hráčů", "hráčů");
        if (k.new_players) text += " (z toho " + plural(k.new_players, "nový", "noví", "nových") + ")";
        text += ". V pokladně ggLeapu utratili " + this.money(k.revenue);
        if (k.revenue && k.revenue_time) {
            text += ", z toho " + Math.round((100 * k.revenue_time) / k.revenue) + " % za hraní";
        }
        text += ".";
        if (k.revenue && (k.revenue_food || 0) < 0.01 * k.revenue) {
            text += " Občerstvení se v ggLeapu skoro nemarkuje, prodej na jiné pokladně tady není vidět.";
        }
        const d = this.state.data;
        if (d.kpi_previous && d.kpi_previous.revenue) {
            const pct = Math.round(((k.revenue / d.kpi_previous.revenue) - 1) * 100);
            if (Math.abs(pct) >= 3) {
                text += " To je o " + Math.abs(pct) + " % " + (pct > 0 ? "víc" : "míň") + " než ve srovnávaném období.";
            } else {
                text += " Zhruba stejně jako ve srovnávaném období.";
            }
        }
        return text;
    }
    delta(key, plain = false) {
        const d = this.state.data;
        if (!d.kpi_previous) return { text: "", cls: "" };
        const now = d.kpi[key] || 0, prev = d.kpi_previous[key] || 0;
        if (!prev) return now ? { text: "nové", cls: "text-success" } : { text: "", cls: "" };
        if (plain) {  // percentages: show the difference in points
            const diff = Math.round(now - prev);
            return { text: (diff >= 0 ? "▲ " : "▼ ") + Math.abs(diff) + " b.", cls: diff >= 0 ? "text-success" : "text-danger" };
        }
        const pct = ((now / prev) - 1) * 100;
        if (pct > 900) return { text: "▲ víc než 10×", cls: "text-success" };
        return { text: (pct >= 0 ? "▲ " : "▼ ") + Math.abs(pct).toFixed(0) + " %", cls: pct >= 0 ? "text-success" : "text-danger" };
    }
    get cards() {
        const k = this.state.data.kpi;
        return [
            { key: "revenue", label: "Tržby", value: this.money(k.revenue),
              hint: "Jen pokladna ggLeapu. Za hraní " + this.money(k.revenue_time) + ", občerstvení " + this.money(k.revenue_food),
              open: () => this.openLines() },
            { key: "visits", label: "Návštěvy", value: this.whole(k.visits),
              hint: "den, kdy hráč přišel · herních sezení " + this.whole(k.sessions),
              open: () => this.openVisits() },
            { key: "players", label: "Různých hráčů", value: this.whole(k.players),
              hint: "průměrně utratil " + this.money(k.avg_per_player), open: () => this.openVisits() },
            { key: "new_players", label: "Noví hráči", value: this.whole(k.new_players),
              hint: "poprvé u nás v tomto období", open: () => this.openNewPlayers() },
            { key: "new_returned_pct", label: "Noví, kteří se vrátili", value: (k.new_players ? k.new_returned_pct : 0) + " %",
              hint: k.new_players ? this.whole(k.new_returned) + " z " + this.whole(k.new_players) + " přišlo znovu do 30 dní" : "žádní noví hráči",
              plain: true, open: () => this.openNewPlayers() },
            { key: "hours_played", label: "Odehráno hodin", value: this.whole(k.hours_played),
              hint: "průměrné sezení " + this.number(k.avg_visit_hours) + " h", open: () => this.openVisits() },
            { key: "hours_free", label: "Rozdáno hodin zdarma", value: this.whole(k.hours_free),
              hint: "dárky, akce a odměny", open: () => this.openLines([["kind", "=", "free"]], "Hraní zdarma") },
            { key: "bookings", label: "Rezervace", value: this.whole(k.bookings),
              hint: k.bookings_noshow ? "nedorazilo: " + this.whole(k.bookings_noshow) : "všichni dorazili nebo teprve přijdou",
              open: () => this.openBookings() },
        ];
    }
    sharePct(value, total) { return total ? Math.round((value / total) * 100) : 0; }

    // ---------- heatmap ----------
    get heat() {
        const grid = this.state.data.heatmap;
        let max = 0, best = null;
        const used = new Set();
        grid.forEach((row, d) => row.forEach((v, h) => {
            if (v) used.add(h);
            if (v > max) { max = v; best = { d, h, v }; }
        }));
        // show the hours the arena is used (from the first to the last used hour), at least 10–23
        let hours = [...used].sort((a, b) => a - b);
        const from = Math.min(hours.length ? hours[0] : 10, 10), to = Math.max(hours.length ? hours[hours.length - 1] : 23, 23);
        hours = [];
        for (let h = from; h <= to; h++) hours.push(h);
        const rows = grid.map((row, d) => ({
            day: DAYS[d], d,
            cells: hours.map((h) => ({ h, v: row[h], style: this.heatStyle(row[h], max) })),
        }));
        let sentence = "";
        if (best) {
            sentence = "Nejvíc lidí přichází " + DAY_NAMES[best.d] + " kolem " + best.h + ":00.";
        }
        return { hours, rows, max, sentence };
    }
    heatStyle(v, max) {
        if (!v || !max) return "background:#f8fafc;color:transparent";
        const a = 0.12 + 0.88 * (v / max);
        return "background:rgba(79,70,229," + a.toFixed(2) + ");color:" + (a > 0.55 ? "#fff" : "#1e1b4b");
    }

    // ---------- segments ----------
    get segments() {
        const rows = this.state.data.segments;
        const total = rows.reduce((s, r) => s + r.count, 0);
        return rows.map((r) => ({ ...r, color: SEGMENT_COLORS[r.key], pct: this.sharePct(r.count, total) }));
    }
    get segmentSentence() {
        const s = Object.fromEntries(this.state.data.segments.map((r) => [r.key, r]));
        /** Czech verb agreement: 1 přestal, 2–4 přestali, 5+ přestalo. */
        const verb = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
        const leaving = (s.ohrozeni?.count || 0) + (s.ztraceni?.count || 0);
        let text = "";
        if (leaving) {
            text += plural(leaving, "pravidelný hráč", "pravidelní hráči", "pravidelných hráčů") + " k nám " +
                verb(leaving, "přestal", "přestali", "přestalo") + " chodit";
            if (s.ohrozeni?.count) {
                text += " (" + this.whole(s.ohrozeni.count) + " z nich teprve nedávno, ty má smysl pozvat zpátky hned)";
            }
            text += ". ";
        }
        const once = s.jednou_davno?.count || 0;
        if (once) {
            text += plural(once, "hráč", "hráči", "hráčů") + " " + verb(once, "přišel", "přišli", "přišlo") +
                " jen jednou a už se " + verb(once, "nevrátil", "nevrátili", "nevrátilo") + ".";
        }
        return text;
    }

    // ---------- drill-down ----------
    utcDomain(field) {
        const p = this.state.data.period;
        return [[field, ">=", p.utc_from], [field, "<", p.utc_to]];
    }
    title(text) { return text + " · " + this.periodLabel(this.state.data.period); }
    openLines(extra = [], title = "Tržby podle položek") {
        this.action.doAction({
            type: "ir.actions.act_window", name: this.title(title), res_model: "elite.arena.ggleap.transaction.line",
            views: [[false, "pivot"], [false, "graph"], [false, "list"]],
            domain: [["is_paid", "=", true], ...this.utcDomain("date"), ...extra],
            context: { pivot_row_groupby: ["name"] },
        });
    }
    openTransactions(extra = [], title = "Prodeje") {
        this.action.doAction({
            type: "ir.actions.act_window", name: this.title(title), res_model: "elite.arena.ggleap.transaction",
            views: [[false, "list"], [false, "pivot"], [false, "form"]],
            domain: [["is_paid", "=", true], ...this.utcDomain("date"), ...extra],
        });
    }
    openVisits(extra = [], title = "Herní sezení") {
        this.action.doAction({
            type: "ir.actions.act_window", name: this.title(title), res_model: "elite.arena.ggleap.visit",
            views: [[false, "list"], [false, "pivot"], [false, "graph"], [false, "form"]],
            domain: [...this.utcDomain("start"), ...extra],
        });
    }
    openNewPlayers() {
        this.action.doAction({
            type: "ir.actions.act_window", name: this.title("Noví hráči"), res_model: "elite.arena.ggleap.player",
            views: [[false, "list"], [false, "form"]], domain: this.utcDomain("first_visit"),
        });
    }
    openBookings() {
        this.action.doAction({
            type: "ir.actions.act_window", name: this.title("Rezervace"), res_model: "elite.arena.ggleap.booking",
            views: [[false, "list"], [false, "calendar"]], domain: this.utcDomain("start"),
        });
    }
    openSegment(row) {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Hráči · " + row.label, res_model: "elite.arena.ggleap.player",
            views: [[false, "list"], [false, "form"]],
            domain: [["segment", "=", row.key], ["deleted", "=", false]],
        });
    }
    openPlayer(row) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "elite.arena.ggleap.player", res_id: row.id,
            views: [[false, "form"]],
        });
    }
    openProduct(row) { this.openLines([["name", "=", row.name]], row.name); }

    // ---------- charts ----------
    destroyCharts() { this.charts.forEach((c) => c.destroy()); this.charts = []; }
    renderCharts() {
        this.destroyCharts();
        const d = this.state.data;
        if (!d || !window.Chart) return;
        const Chart = window.Chart;
        const moneyTick = (v) => money.format(v);

        let rows = d.daily, labels;
        if (rows.length > 62) {  // long periods: per month
            const months = {};
            for (const r of rows) {
                const key = r.date.slice(0, 7);
                months[key] = months[key] || { date: key, time: 0, food: 0, other: 0, visits: 0 };
                for (const k of ["time", "food", "other", "visits"]) months[key][k] += r[k];
            }
            rows = Object.values(months);
            labels = rows.map((r) => r.date.slice(5, 7) + "/" + r.date.slice(0, 4));
        } else {
            labels = rows.map((r) => { const x = parseIso(r.date); return DAYS[(x.getDay() + 6) % 7] + " " + x.getDate() + ". " + (x.getMonth() + 1) + "."; });
        }
        if (this.refs.daily.el) {
            this.charts.push(new Chart(this.refs.daily.el, {
                type: "bar",
                data: {
                    labels,
                    datasets: [
                        ...["time", "food", "other"].map((k) => ({
                            label: KIND_LABELS[k], data: rows.map((r) => r[k]), backgroundColor: COLORS[k],
                            stack: "revenue", yAxisID: "y", order: 2 })),
                        { type: "line", label: "Návštěvy", data: rows.map((r) => r.visits), borderColor: COLORS.visits,
                          backgroundColor: COLORS.visits, borderWidth: 2, pointRadius: 2, tension: 0.25, yAxisID: "y2", order: 1 },
                    ],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (ctx) =>
                        ctx.dataset.label + ": " + (ctx.dataset.yAxisID === "y2" ? whole.format(ctx.parsed.y) : money.format(ctx.parsed.y)) } } },
                    scales: {
                        x: { stacked: true },
                        y: { stacked: true, ticks: { callback: moneyTick }, title: { display: true, text: "Tržby" } },
                        y2: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true,
                              title: { display: true, text: "Návštěvy" } },
                    },
                },
            }));
        }
        if (this.refs.payments.el && d.payment_methods.length) {
            const pm = d.payment_methods;
            this.charts.push(new Chart(this.refs.payments.el, {
                type: "doughnut",
                data: { labels: pm.map((r) => r.label), datasets: [{ data: pm.map((r) => r.amount), backgroundColor: pm.map((_r, i) => PALETTE[i]) }] },
                options: { maintainAspectRatio: false, plugins: { legend: { position: "right" },
                           tooltip: { callbacks: { label: (ctx) => ctx.label + ": " + money.format(ctx.parsed) } } },
                           onClick: (_e, els) => {
                               if (!els.length) return;
                               const field = { cash: "paid_cash", card: "paid_card", balance: "paid_balance" }[pm[els[0].index].method];
                               this.openTransactions([[field, ">", 0]], pm[els[0].index].label);
                           } },
            }));
        }
        if (this.refs.machines.el && d.machines.length) {
            const ms = d.machines;
            this.charts.push(new Chart(this.refs.machines.el, {
                type: "bar",
                data: { labels: ms.map((m) => m.name), datasets: [{ label: "Odehráno hodin", data: ms.map((m) => m.hours), backgroundColor: COLORS.time }] },
                options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false },
                           tooltip: { callbacks: { label: (ctx) => number.format(ctx.parsed.x) + " h, " + ms[ctx.dataIndex].visits + " návštěv" } } },
                           onClick: (_e, els) => { if (els.length) { const m = ms[els[0].index]; this.openVisits([["place", "=", m.name]], m.name); } } },
            }));
        }
    }
    get machinesHeight() { return Math.max(160, 22 * (this.state.data.machines.length || 1) + 40); }
}

registry.category("actions").add("elite_arena_ggleap.dashboard", GgleapDashboard);
