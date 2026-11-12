/** @odoo-module */

import { Component } from "@odoo/owl";

export class EliteClosingReceipt extends Component {
    static template = "elite_pos_closing_receipt.ClosingReceipt";
    static props = {
        data: Object,
        cashier: { type: String, optional: true },
        withProducts: { type: Boolean, optional: true },
        formatCurrency: Function,
    };

    money(value) {
        return this.props.formatCurrency(value || 0);
    }

    qty(value) {
        return new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 3 }).format(value || 0);
    }

    dateTime(value) {
        if (!value) {
            return "";
        }
        // Odoo sends UTC "YYYY-MM-DD HH:MM:SS"; the till shows Prague time.
        const date = value instanceof Date ? value : new Date(String(value).replace(" ", "T") + "Z");
        return date.toLocaleString("cs-CZ", { timeZone: "Europe/Prague" });
    }

    get printedAt() {
        return this.dateTime(new Date());
    }
}
