/** @odoo-module **/
// Goods receipt by scanner (client action elite_vet_sale.goods_receipt, spec §6).
// Scanners type the code and Enter into the always-focused scan field; the backend
// (models/goods_receipt.py) parses GS1 / EAN codes, "Naskladnit" creates the receipt + expense.
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount, useExternalListener } from "@odoo/owl";

const MODEL = "elite.vet.goods.receipt";
const SEARCH_DELAY = 250;
const GS = "\x1d";

const NF = new Intl.NumberFormat("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function fmtMoney(value) { return NF.format(value || 0) + " Kč"; }
function parseNum(value) {
    const n = parseFloat(String(value ?? "").replace(/\s/g, "").replace(",", "."));
    return Number.isFinite(n) ? n : 0;
}
function inputNum(value) { return value === null || value === undefined ? "" : String(value).replace(".", ","); }
function errorMessage(e) { return e?.data?.message || e?.message || String(e); }
function lineKey(productId, lot) { return productId + "|" + (lot || "").trim(); }

export class GoodsReceipt extends Component {
    static template = "elite_vet_sale.GoodsReceipt";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            supplier: null, supplierTerm: "", suppliers: [], supplierOpen: false, supplierActive: 0,
            lines: [], lastKey: null, lotPromptKey: null,
            pending: null, productTerm: "", products: [], productActive: 0,
            documentNumber: "", busy: false, scanning: 0, lastError: "",
        });
        this.scanRef = useRef("scan");
        this.supplierRef = useRef("supplier");
        this.productRef = useRef("product");
        this.lotRef = useRef("lot");
        this.queue = Promise.resolve();
        this.seq = 0;
        this.nextId = 1;
        useExternalListener(window, "mousedown", (ev) => {
            if (!ev.target.closest?.(".evgr-supplier")) this.state.supplierOpen = false;
        });
        // A click anywhere but into a field gives the focus back to the scan field.
        useExternalListener(window, "mouseup", (ev) => {
            if (!ev.target.closest?.("input, textarea, select, .evgr-modal, .evgr-supplier")) this.focusScan();
        });
        onMounted(() => { this.focusScan(); this.loadSuppliers(""); });
        onWillUnmount(() => { clearTimeout(this.supplierTimer); clearTimeout(this.productTimer); });
    }

    // ------------------------------------------------------------ focus
    focusScan() {
        setTimeout(() => {
            if (this.state.pending) return this.productRef.el?.focus();
            if (this.state.lotPromptKey && this.lotRef.el) return this.lotRef.el.focus();
            this.scanRef.el?.focus();
        });
    }

    // ------------------------------------------------------------ supplier
    async loadSuppliers(term) {
        const seq = ++this.seq;
        const suppliers = await this.orm.call(MODEL, "suppliers", [term, 20]);
        if (seq !== this.seq) return;
        Object.assign(this.state, { suppliers, supplierActive: 0 });
    }
    onSupplierFocus() {
        this.state.supplierOpen = true;
        this.loadSuppliers(this.state.supplierTerm.trim());
    }
    onSupplierInput(ev) {
        this.state.supplierTerm = ev.target.value;
        this.state.supplierOpen = true;
        clearTimeout(this.supplierTimer);
        this.supplierTimer = setTimeout(() => this.loadSuppliers(this.state.supplierTerm.trim()), SEARCH_DELAY);
    }
    get canCreateSupplier() {
        const term = this.state.supplierTerm.trim().toLowerCase();
        return term.length >= 2 && !this.state.suppliers.some((s) => s.name.toLowerCase() === term);
    }
    onSupplierKeydown(ev) {
        const n = this.state.suppliers.length + (this.canCreateSupplier ? 1 : 0);
        if (ev.key === "ArrowDown" && n) {
            ev.preventDefault();
            this.state.supplierActive = (this.state.supplierActive + 1) % n;
        } else if (ev.key === "ArrowUp" && n) {
            ev.preventDefault();
            this.state.supplierActive = (this.state.supplierActive - 1 + n) % n;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const s = this.state.suppliers[this.state.supplierActive];
            if (s) this.selectSupplier(s);
            else if (this.canCreateSupplier) this.createSupplier();
        } else if (ev.key === "Escape") {
            this.state.supplierOpen = false;
            this.focusScan();
        }
    }
    selectSupplier(supplier) {
        Object.assign(this.state, { supplier, supplierTerm: "", supplierOpen: false });
        this.focusScan();
    }
    changeSupplier() {
        this.state.supplier = null;
        setTimeout(() => this.supplierRef.el?.focus());
    }
    async createSupplier() {
        try {
            const supplier = await this.orm.call(MODEL, "create_supplier", [this.state.supplierTerm]);
            this.selectSupplier(supplier);
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
        }
    }

    // ------------------------------------------------------------ scanning
    onScanKeydown(ev) {
        if (ev.ctrlKey && (ev.key === "]" || ev.code === "BracketRight")) {
            // FNC1 of keyboard-wedge scanners (Ctrl+]) -> GS separator
            ev.preventDefault();
            const el = ev.target;
            const pos = el.selectionStart ?? el.value.length;
            el.value = el.value.slice(0, pos) + GS + el.value.slice(el.selectionEnd ?? pos);
            el.selectionStart = el.selectionEnd = pos + 1;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const code = ev.target.value;
            ev.target.value = "";
            if (code.trim()) this.enqueue(code);
        }
    }
    enqueue(code) {
        // One scan after another: a second beep of the same lot must find the first line.
        this.state.scanning++;
        this.queue = this.queue.then(() => this.processScan(code)).catch((e) => {
            this.state.lastError = errorMessage(e);
            this.notification.add(this.state.lastError, { type: "danger" });
        }).finally(() => { this.state.scanning--; this.focusScan(); });
    }
    async processScan(code) {
        const res = await this.orm.call(MODEL, "scan", [code]);
        this.state.lastError = "";
        if (!res.known) {
            Object.assign(this.state, {
                pending: { code: code.trim(), lot: res.lot, expiry: res.expiry },
                productTerm: "", products: [], productActive: 0,
            });
            return;
        }
        this.addLine(res);
    }
    addLine(res) {
        const tracked = res.product.tracking !== "none";
        const lot = tracked ? (res.lot || "") : "";
        const key = lineKey(res.product.id, lot);
        const existing = this.state.lines.find((l) => l.key === key);
        if (existing) {
            existing.quantity += 1;
            if (res.expiry && !existing.expiry) existing.expiry = res.expiry;
        } else {
            this.state.lines.unshift({
                id: this.nextId++, key, product: res.product, tracked, lot, expiry: res.expiry || "",
                quantity: 1, unit_cost: res.suggested_cost || 0, vat_rate: res.vat_rate || 0,
            });
        }
        this.state.lastKey = key;
        this.state.lotPromptKey = tracked && !lot ? key : null;
    }

    // ------------------------------------------------------------ unknown code -> product
    onProductInput(ev) {
        this.state.productTerm = ev.target.value;
        clearTimeout(this.productTimer);
        const term = this.state.productTerm.trim();
        if (term.length < 2) {
            this.state.products = [];
            return;
        }
        this.productTimer = setTimeout(async () => {
            const products = await this.orm.call(MODEL, "search_products", [term, 20]);
            if (term === this.state.productTerm.trim()) Object.assign(this.state, { products, productActive: 0 });
        }, SEARCH_DELAY);
    }
    onProductKeydown(ev) {
        const n = this.state.products.length;
        if (ev.key === "ArrowDown" && n) {
            ev.preventDefault();
            this.state.productActive = (this.state.productActive + 1) % n;
        } else if (ev.key === "ArrowUp" && n) {
            ev.preventDefault();
            this.state.productActive = (this.state.productActive - 1 + n) % n;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            if (n) this.assignProduct(this.state.products[this.state.productActive]);
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.cancelPending();
        }
    }
    async assignProduct(product) {
        const pending = this.state.pending;
        try {
            const res = await this.orm.call(MODEL, "assign_code", [pending.code, product.id]);
            this.state.pending = null;
            this.addLine(res);
            this.notification.add(`Kód je přiřazený k produktu ${product.name}.`, { type: "info" });
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger" });
        }
        this.focusScan();
    }
    cancelPending() {
        this.state.pending = null;
        this.focusScan();
    }

    // ------------------------------------------------------------ lines
    merge(line) {
        // an edited lot can make two lines the same product + lot -> one line
        line.key = lineKey(line.product.id, line.lot);
        const other = this.state.lines.find((l) => l !== line && l.key === line.key);
        if (other) {
            other.quantity += line.quantity;
            other.expiry = other.expiry || line.expiry;
            this.state.lines.splice(this.state.lines.indexOf(line), 1);
        }
        this.state.lastKey = line.key;
    }
    onLotChange(line, ev) {
        line.lot = ev.target.value.trim();
        this.merge(line);
        if (this.state.lotPromptKey && (line.lot || !this.state.lines.includes(line))) this.state.lotPromptKey = null;
        this.focusScan();
    }
    onLotKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.target.blur();   // change -> onLotChange
        }
    }
    onFieldKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.target.blur();
            this.focusScan();
        }
    }
    onExpiryChange(line, ev) { line.expiry = ev.target.value; this.state.lastKey = line.key; }
    onQtyChange(line, ev) {
        const qty = parseNum(ev.target.value);
        if (qty > 0) line.quantity = qty;
        ev.target.value = inputNum(line.quantity);
        this.state.lastKey = line.key;
    }
    onCostChange(line, ev) {
        line.unit_cost = Math.max(parseNum(ev.target.value), 0);
        ev.target.value = inputNum(line.unit_cost);
        this.state.lastKey = line.key;
    }
    step(line, delta) {
        line.quantity = Math.max(1, line.quantity + delta);
        this.state.lastKey = line.key;
        this.focusScan();
    }
    remove(line) {
        this.state.lines.splice(this.state.lines.indexOf(line), 1);
        if (this.state.lotPromptKey === line.key) this.state.lotPromptKey = null;
        this.focusScan();
    }
    lineTotal(line) { return line.quantity * line.unit_cost; }
    get totals() {
        let untaxed = 0, total = 0;
        for (const l of this.state.lines) {
            untaxed += this.lineTotal(l);
            total += this.lineTotal(l) * (1 + l.vat_rate / 100);
        }
        return { untaxed, total };
    }
    get missingLots() { return this.state.lines.filter((l) => l.tracked && !l.lot); }
    get canValidate() {
        return this.state.supplier && this.state.lines.length && !this.missingLots.length && !this.state.busy;
    }
    fmtMoney(v) { return fmtMoney(v); }
    inputNum(v) { return inputNum(v); }

    // ------------------------------------------------------------ Naskladnit
    async validate() {
        if (!this.canValidate) return;
        this.state.busy = true;
        try {
            await this.queue;   // scans still on their way belong to this receipt
            const lines = this.state.lines.map((l) => ({
                product_id: l.product.id, lot: l.lot || null, expiry: l.expiry || null,
                quantity: l.quantity, unit_cost: l.unit_cost,
            }));
            const res = await this.orm.call(MODEL, "validate",
                [this.state.supplier.id, lines, this.state.documentNumber.trim() || null]);
            this.notification.add(`Naskladněno: ${res.picking_name}` + (res.expense_id ? ", výdaj zapsán." : "."),
                { type: "success", title: "Příjem zboží" });
            Object.assign(this.state, { lines: [], lastKey: null, lotPromptKey: null, documentNumber: "" });
        } catch (e) {
            this.notification.add(errorMessage(e), { type: "danger", title: "Příjem zboží" });
        } finally {
            this.state.busy = false;
            this.focusScan();
        }
    }
}

registry.category("actions").add("elite_vet_sale.goods_receipt", GoodsReceipt);
