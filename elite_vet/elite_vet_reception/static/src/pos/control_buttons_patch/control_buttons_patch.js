/**
 * Pokladna (product screen): button "Klient" - Kartotéka in the order mode ("Vybrat k účtu").
 * In the reception till it is the only way to set the customer of an order: the standard customer
 * button is hidden (control buttons, mobile action pad) and the standard partner list, which the
 * payment screen still opens (Zákazník, invoice), is replaced by the same Kartotéka, so the Task 5
 * rules (a bill of another client is never handed over) always apply.
 */
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";

export class ReceptionClientButton extends Component {
    static template = "elite_vet_reception.ReceptionClientButton";
    // the customer of the current order, shown on the button
    static props = { partner: { type: [Object, { value: null }, { value: false }], optional: true } };

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
    }

    onClick() {
        this.dialog.add(CardIndexDialog, { mode: "order" });
    }
}

patch(ControlButtons, {
    components: { ...ControlButtons.components, ReceptionClientButton },
});

patch(ActionpadWidget, {
    components: { ...ActionpadWidget.components, ReceptionClientButton },
});

patch(PosStore.prototype, {
    async selectPartner() {
        const order = this.get_order();
        // refund lines: the standard alert (the customer cannot be changed) stays
        if (!this.isReceptionPos || !order || (order.get_partner() && order.getHasRefundLines())) {
            return super.selectPartner(...arguments);
        }
        this.dialog.add(CardIndexDialog, { mode: "order" });
        return order.get_partner();
    },
});
