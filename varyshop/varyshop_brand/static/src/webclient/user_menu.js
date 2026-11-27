import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { BRAND_URL } from "../brand";

const items = registry.category("user_menuitems");

// No "My Odoo.com account"; documentation leads to Varyshop (support: session.support_url, see
// models/ir_http.py).
items.remove("odoo_account");
items.add(
    "documentation",
    () => {
        const url = `${BRAND_URL}?utm_source=db&utm_medium=documentation`;
        return {
            type: "item",
            id: "documentation",
            description: _t("Documentation"),
            href: url,
            callback: () => browser.open(url, "_blank"),
            sequence: 10,
        };
    },
    { force: true }
);
