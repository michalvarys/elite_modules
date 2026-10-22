/** Reception API in the POS: calls of `elite.vet.reception` with Czech error messages. */
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";

const MODEL = "elite.vet.reception";
// Screen names = class names: the POS keeps `mainScreen.component.name` as the previous screen
// (pos_hr returns to it after the PIN login).
export const TODAY_SCREEN = "ReceptionTodayScreen";
export const BOOKING_SCREEN = "ReceptionBookingScreen";
export const BOARD_URL = "/odoo/action-elite_vet_reservation.action_board";
export const CLINIC_TZ = "Europe/Prague";

/** Today in the clinic as "YYYY-MM-DD". */
export function clinicToday() {
    return luxon.DateTime.now().setZone(CLINIC_TZ).toISODate();
}

/** "YYYY-MM-DD" shifted by `days`. */
export function shiftDay(isoDay, days) {
    return luxon.DateTime.fromISO(isoDay).plus({ days }).toISODate();
}

/** "čt 29. 10. 2026" */
export function dayLabel(isoDay) {
    return luxon.DateTime.fromISO(isoDay).setLocale("cs").toFormat("ccc d. L. yyyy");
}

/** "4. 5. 2020" */
export function shortDate(isoDay) {
    return luxon.DateTime.fromISO(isoDay).toFormat("d. L. yyyy");
}

/** Czech text for an error of an API call. */
export function errorMessage(error) {
    if (error instanceof RPCError) {
        return error.data?.message || error.message || "Akce se nepodařila.";
    }
    if (error instanceof ConnectionLostError) {
        return "Spojení se serverem se přerušilo – zkuste to prosím znovu.";
    }
    return error?.message || "Akce se nepodařila.";
}

/**
 * `orm.call("elite.vet.reception", method, args)`; a failure is shown as a POS notification
 * and the call returns `undefined` (unless `rethrow`).
 */
export async function callReception(orm, notification, method, args = [], { rethrow = false } = {}) {
    try {
        return await orm.call(MODEL, method, args);
    } catch (error) {
        notification.add(errorMessage(error), { type: "danger", sticky: false });
        if (rethrow) {
            throw error;
        }
        return undefined;
    }
}
