/** Varyshop instead of Odoo in texts shown to users: dialog titles (errors, warnings, "Odoo Server
 * Error" in any language) and the browser tab title. */
import { markup } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

export const BRAND_NAME = "Varyshop";
export const BRAND_URL = "https://www.varyshop.eu";

const ODOO = /\bOdoo\b/g;
const Markup = markup("").constructor;

/** Text with "Odoo" replaced; markup stays markup, anything without "Odoo" is returned as it is. */
export function rebrand(text) {
    if (text === undefined || text === null || typeof text === "number") {
        return text;
    }
    const value = String(text);
    if (!value.match(ODOO)) {
        return text;
    }
    const branded = value.replace(ODOO, BRAND_NAME);
    return text instanceof Markup ? markup(branded) : branded;
}

patch(Dialog.prototype, {
    get brandedTitle() {
        return rebrand(this.props.title);
    },
});

// The title service falls back to "Odoo" when no part is set; parts naming Odoo are rebranded.
const titleService = registry.category("services").get("title", null);
if (titleService) {
registry.category("services").add(
    "title",
    {
        ...titleService,
        start(env, deps) {
            const service = titleService.start(env, deps);
            const setParts = service.setParts;
            service.setParts = (parts) => {
                const branded = {};
                for (const key in parts) {
                    branded[key] = rebrand(parts[key]);
                }
                setParts(branded);
                if (!document.title || document.title === "Odoo") {
                    document.title = BRAND_NAME;
                }
            };
            return service;
        },
    },
    { force: true }
);
}
