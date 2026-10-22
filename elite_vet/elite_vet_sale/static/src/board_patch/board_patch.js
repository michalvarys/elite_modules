/** @odoo-module **/
// Reservation board: payment chip on a reservation card ("k pokladně" / "zaplaceno").
import { patch } from "@web/core/utils/patch";
import { ReservationBoard } from "@elite_vet_reservation/board/board";

patch(ReservationBoard.prototype, {
    paymentChip(e) {
        if (e.payment_state === "waiting") {
            return { cls: "evsl-chip-waiting", text: "k pokladně", title: "Čeká na platbu v pokladně" };
        }
        if (e.payment_state === "partial") {
            return { cls: "evsl-chip-waiting", text: "k pokladně", title: "Částečně zaplaceno" };
        }
        if (e.payment_state === "paid") {
            return { cls: "evsl-chip-paid", text: "zaplaceno", title: "Zaplaceno" };
        }
        return false;
    },
});
