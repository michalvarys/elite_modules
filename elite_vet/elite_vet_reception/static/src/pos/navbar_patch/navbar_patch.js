/** Reception tabs in the POS navbar (only in the "Recepce" till). */
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
import { BoardDialog } from "@elite_vet_reception/pos/board_dialog/board_dialog";
import { BOOKING_SCREEN, TODAY_SCREEN } from "@elite_vet_reception/pos/reception_api";

export class ReceptionTabs extends Component {
    static template = "elite_vet_reception.ReceptionTabs";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.ui = useService("ui");
    }

    get tabs() {
        return [
            { key: "today", label: "Dnes", icon: "fa-sun-o", screen: TODAY_SCREEN },
            { key: "card", label: "Kartotéka…", icon: "fa-address-book-o" },
            { key: "booking", label: "Objednat", icon: "fa-calendar-plus-o", screen: BOOKING_SCREEN },
            { key: "till", label: "Pokladna", icon: "fa-shopping-basket", screen: "ProductScreen" },
            { key: "board", label: "Tabule", icon: "fa-calendar" },
        ];
    }

    isActive(tab) {
        return tab.screen && this.pos.mainScreen.component?.name === tab.screen;
    }

    onClick(tab) {
        if (tab.key === "card") {
            this.dialog.add(CardIndexDialog, {});
        } else if (tab.key === "board") {
            this.dialog.add(BoardDialog, {});
        } else {
            this.pos.showScreen(tab.screen);
        }
    }
}

patch(Navbar, {
    components: { ...Navbar.components, ReceptionTabs },
});
