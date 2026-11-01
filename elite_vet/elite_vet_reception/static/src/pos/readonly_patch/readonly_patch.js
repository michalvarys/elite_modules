/**
 * Read-only mode (Nastavení → Elite Vet, production while the clinic works in WinVet): the till
 * opens and shows everything, but a sale is never paid. The server refuses it too (pos.order).
 */
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        if (this.pos.config.elite_vet_readonly) {
            this.dialog.add(AlertDialog, {
                title: "Jen pro čtení",
                body: "Pokladna je zatím jen pro čtení – prodává se ve WinVetu. Účet se neuloží.",
            });
            return;
        }
        return super.validateOrder(...arguments);
    },
});
