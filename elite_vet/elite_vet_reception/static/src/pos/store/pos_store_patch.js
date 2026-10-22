/**
 * Reception till ("Recepce"): Dnes is the screen after loading the POS and after the PIN login,
 * and a visit bill is paid through pos_sale's settle flow (without its option popup).
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { TODAY_SCREEN } from "@elite_vet_reception/pos/reception_api";

patch(PosStore.prototype, {
    get isReceptionPos() {
        return Boolean(this.config?.is_elite_vet_reception);
    },

    get firstScreen() {
        const screen = super.firstScreen;
        return screen === "ProductScreen" && this.isReceptionPos ? TODAY_SCREEN : screen;
    },

    showScreen(name, props) {
        // After the PIN login pos_hr returns to the screen before the login screen, or to the
        // product screen when there was none (POS just loaded) - the reception starts in Dnes.
        if (
            name === "ProductScreen" &&
            this.isReceptionPos &&
            this.mainScreen?.component?.name === "LoginScreen" &&
            this.previousScreen !== "ProductScreen"
        ) {
            name = TODAY_SCREEN;
        }
        return super.showScreen(name, props);
    },

    /**
     * Load the visit bill (sale.order) into the till and open the payment screen.
     * Same as pos_sale `onClickSaleOrder` → "Settle the order", but the bill always gets an
     * order of its own unless the current order is empty and has no other customer, so two
     * clients never end up on one receipt.
     */
    async payReceptionBill(saleOrderId) {
        if (this.shouldShowOpeningControl()) {
            this.notification.add("Nejdřív otevřete pokladnu (počáteční stav hotovosti).", { type: "warning" });
            this.openOpeningControl();
            return null;
        }
        const saleOrder = await this._getSaleOrder(saleOrderId);
        let order = this.get_order();
        const lines = order ? order.get_orderlines() : [];
        const alreadyLoaded =
            lines.length > 0 && lines.every((line) => line.sale_order_origin_id?.id === saleOrder.id);
        if (!alreadyLoaded) {
            const partner = order?.get_partner();
            const otherClient = partner && partner.id !== saleOrder.partner_id?.id;
            if (!order || order.finalized || lines.length || otherClient) {
                order = this.add_new_order();
            }
            if (saleOrder.partner_id) {
                order.set_partner(saleOrder.partner_id);
            }
            // fiscal position after the partner, as pos_sale does
            const fiscalPosition = saleOrder.fiscal_position_id;
            order.update({ fiscal_position_id: fiscalPosition });
            await this.settleSO(saleOrder, fiscalPosition);
        }
        this.showScreen("PaymentScreen", { orderUuid: order.uuid });
        return order;
    },
});
