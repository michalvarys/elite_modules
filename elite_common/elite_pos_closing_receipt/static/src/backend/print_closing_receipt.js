/** @odoo-module */

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
    frame.src = `/report/html/elite_pos_closing_receipt.report_closing_receipt/${ids.join(",")}`;
    await new Promise((resolve, reject) => {
        frame.onload = resolve;
        frame.onerror = reject;
        document.body.appendChild(frame);
    });
    try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
    } finally {
        // print() returns once the dialog is closed; keep the frame a moment for slow print previews.
        setTimeout(() => frame.remove(), 60000);
    }
}

registry.category("actions").add("elite_pos_closing_receipt.print", printClosingReceipt);
