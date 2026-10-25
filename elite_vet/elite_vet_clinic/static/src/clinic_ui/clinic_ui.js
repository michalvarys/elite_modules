/** @odoo-module **/
// Shared pieces of the clinical screens (task 26): the visit tile of the screen Ordinace
// (elite_vet_reception) and of Moji pacienti dnes. Template elite_vet_clinic.VisitTileBody,
// styles in clinic_ui.scss (.ev-clinic tokens, .evt tile).

export const VISIT_STATES = ["waiting", "in_room", "booked", "done"];

/** "Čeká 33 min" / "V ordinaci od 21:37" / "Objednáno" / "Hotovo". */
export function visitStateText(state, it) {
    if (state === "waiting") {
        const min = it.waiting_minutes;
        return min !== null && min !== undefined ? "Čeká " + min + " min" : "Čeká";
    }
    if (state === "in_room") return it.called_time ? "V ordinaci od " + it.called_time : "V ordinaci";
    if (state === "done") return "Hotovo";
    return "Objednáno";
}

/** Czech plural: plural(2, "pacient", "pacienti", "pacientů"). */
export function plural(n, one, few, many) {
    if (n === 1) return one;
    return n >= 2 && n <= 4 ? few : many;
}

/**
 * Data of a tile from an item of room_board or my_patients_today.
 * state: waiting | in_room | booked | done. opts: {stateText, doctor, room, roomColor}.
 * The big time is the arrival (or the booked time before arrival); the second line says when
 * it was booked when that differs, or "bez objednání".
 */
export function visitTile(it, state, opts = {}) {
    const arrived = it.arrived_time;
    const booked = it.reservation_time || (it.walk_in ? null : it.time);
    let timeSub = null;
    if (it.walk_in) {
        timeSub = "bez objednání";
    } else if (arrived && booked && booked !== arrived) {
        timeSub = "obj. " + booked;
    }
    return {
        state,
        time: arrived || it.time || null,
        timeSub,
        stateText: opts.stateText || visitStateText(state, it),
        pet: it.pet_name || "Bez mazlíčka",
        species: it.species_label || null,
        owner: it.owner || null,
        procedure: it.procedure || null,
        doctor: "doctor" in opts ? opts.doctor : it.doctor || null,
        room: opts.room || null,
        roomColor: opts.roomColor || null,
        alerts: it.alerts || null,
        note: it.reception_note || null,
    };
}
