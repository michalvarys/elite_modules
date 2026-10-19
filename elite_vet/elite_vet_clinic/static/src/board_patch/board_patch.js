/** @odoo-module **/
// Reservation board (elite_vet_reservation): a small "Karta" button on every reservation card
// that has a pet or a client. It goes through the reservation's own action
// (action_open_patient_card), so a web booking is matched with its client and pet first.
import { patch } from "@web/core/utils/patch";
import { ReservationBoard } from "@elite_vet_reservation/board/board";

patch(ReservationBoard.prototype, {
    hasPatientCard(e) {
        return e.kind !== "block" && !!(e.pet || e.owner) && !["cancelled", "web_new"].includes(e.state);
    },
    async openPatientCard(e) {
        try {
            const action = await this.orm.call("elite.vet.reservation", "action_open_patient_card", [[e.id]]);
            await this.action.doAction(action);
        } catch (err) {
            this.notification.add(err.data?.message || err.message, { type: "danger" });
            this.load(true).catch(() => {});   // matching a web booking may have changed the board
        }
    },
});
