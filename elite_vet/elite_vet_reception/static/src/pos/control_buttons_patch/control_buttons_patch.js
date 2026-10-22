/** Pokladna (product screen): button "Klient" - Kartotéka in the order mode ("Vybrat k účtu"). */
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";

export class ReceptionClientButton extends Component {
    static template = "elite_vet_reception.ReceptionClientButton";
    static props = {};

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
