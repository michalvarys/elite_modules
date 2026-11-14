/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * Prints the closing receipt of POS sessions straight through the browser's print dialog.
 *
 * Odoo's report viewer prints by converting to PDF and downloading it; the tills print through the
 * browser dialog instead, so the receipt HTML is loaded into a hidden frame and printed from there.
 */
async function printClosingReceipt(env, action) {
    const ids = action.params?.session_ids || [];
    if (!ids.length) {
        return;
    }
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
    const context = encodeURIComponent(JSON.stringify(action.params.context || {}));
    frame.src = `/report/html/elite_pos_closing_receipt.report_closing_receipt/${ids.join(",")}?context=${context}`;
    await new Promise((resolve, reject) => {
        frame.onload = resolve;
        frame.onerror = reject;
        document.body.appendChild(frame);
    });
    if (!frame.contentDocument?.querySelector(".elite-cr")) {
        // An error page came back instead of the receipt: say so, never print it.
        frame.remove();
        env.services.notification.add(
            _t("Uzávěrku se nepodařilo načíst. Zkontrolujte, že máte přístup k firmě této směny."),
            { type: "danger" }
        );
        return;
    }
    try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
    } finally {
        // print() returns once the dialog is closed; keep the frame a moment for slow print previews.
        setTimeout(() => frame.remove(), 60000);
    }
}

registry.category("actions").add("elite_pos_closing_receipt.print", printClosingReceipt);
