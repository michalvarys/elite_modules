/** @odoo-module */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { EliteClosingReceipt } from "@elite_pos_closing_receipt/closing_receipt/closing_receipt";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup();
        this.printer = useService("printer");
        this.closingPrint = useState({ busy: false, withProducts: false });
    },

    async printClosingReceipt() {
        if (this.closingPrint.busy) {
            return;
        }
        this.closingPrint.busy = true;
        let step = "data";
        try {
            const data = await this.pos.data.call("pos.session", "get_elite_closing_receipt", [
                this.pos.session.id,
            ]);
            step = "print";
            await this.printer.print(
                EliteClosingReceipt,
                {
                    data,
                    cashier: this.pos.get_cashier()?.name || "",
                    withProducts: this.closingPrint.withProducts,
                    formatCurrency: (amount) => this.env.utils.formatCurrency(amount),
                },
                { webPrintFallback: true }
            );
        } catch (error) {
            console.error("Closing receipt failed at step", step, error);
            const detail = error?.data?.message || error?.message || String(error);
            this.dialog.add(AlertDialog, {
                title:
                    step === "data"
                        ? _t("Data uzávěrky se nepodařilo načíst ze serveru")
                        : _t("Uzávěrku se nepodařilo vytisknout"),
                body: _t("Chyba: %s", detail),
            });
        } finally {
            this.closingPrint.busy = false;
        }
    },
});
