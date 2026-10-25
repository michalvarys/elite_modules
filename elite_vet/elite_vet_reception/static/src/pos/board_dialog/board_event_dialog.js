/**
 * Detail of a reservation on the till's board: client, pet, procedure, doctor, time and state,
 * and the actions Přijmout (today only, no visit yet), Klient… (Kartotéka for the reservation),
 * Přesunout (Objednat in the move mode), Zrušit rezervaci and Nedorazil (both with a confirm step
 * in the dialog).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { callReception } from "@elite_vet_reception/pos/reception_api";
import { NoteDialog } from "@elite_vet_reception/pos/note_dialog/note_dialog";

export class BoardEventDialog extends Component {
    static template = "elite_vet_reception.BoardEventDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        reservationId: Number,
        onChanged: Function, // the board reloads
        onClient: Function, // (detail) → Kartotéka in the reservation mode
        onMove: Function, // (detail) → Objednat in the move mode
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({ detail: null, busy: false, confirmCancel: false, confirmNoShow: false });
        onWillStart(() => this.load());
    }

    async load() {
        const detail = await callReception(this.orm, this.notification, "board_reservation", [
            this.props.reservationId,
        ]);
        if (detail) {
            this.state.detail = detail;
        } else {
            this.props.close();
        }
    }

    get detail() {
        return this.state.detail;
    }

    get title() {
        const d = this.detail;
        return d ? `Rezervace ${d.date_label}, ${d.time_label}` : "Rezervace";
    }

    get stateLabel() {
        const d = this.detail;
        if (d.has_record) {
            return d.visit_label ? `přijato – ${d.visit_label}` : "přijato";
        }
        return d.state_label;
    }

    /** Klient… only while the client can still change (not cancelled, done or no-show). */
    get canChangeClient() {
        return !["cancelled", "done", "no_show"].includes(this.detail.state);
    }

    get cancelQuestion() {
        return this.detail.cancel_sends_email
            ? "Opravdu zrušit? Klientovi odejde e-mail o zrušení."
            : "Opravdu zrušit tuto rezervaci?";
    }

    get noShowQuestion() {
        const d = this.detail;
        const who = [d.pet_name, d.owner].filter(Boolean).join(" · ") || "klienta";
        return `Označit ${who} v ${d.time} jako nedorazil?`;
    }

    get confirming() {
        return this.state.confirmCancel || this.state.confirmNoShow;
    }

    async run(action) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await action();
        } finally {
            this.state.busy = false;
        }
    }

    /** Přijmout with an optional internal note for the room (same dialog as in Dnes). */
    checkIn() {
        const detail = this.detail;
        this.dialog.add(NoteDialog, {
            title: `Přijmout: ${[detail.pet_name, detail.owner].filter(Boolean).join(" · ")}`,
            label: "Interní poznámka pro ordinaci (nepovinné)",
            hint: "Uvidí ji sestra a lékařka v ordinaci, klient nikde. Enter = Přijmout.",
            confirmLabel: "Přijmout do čekárny",
            onConfirm: async (note) => {
                const result = await callReception(this.orm, this.notification, "check_in", [
                    detail.main_id,
                    this.pos.get_cashier()?.name || null,
                    note || null,
                ]);
                if (result) {
                    this.notification.add(`${result.pet_name} je v čekárně.`, { type: "success" });
                    this.props.onChanged();
                    this.props.close();
                }
                return Boolean(result);
            },
        });
    }

    openClient() {
        const detail = this.detail;
        this.props.close();
        this.props.onClient(detail);
    }

    move() {
        const detail = this.detail;
        this.props.close();
        this.props.onMove(detail);
    }

    askCancel() {
        this.state.confirmCancel = true;
    }

    keep() {
        this.state.confirmCancel = false;
        this.state.confirmNoShow = false;
    }

    askNoShow() {
        this.state.confirmNoShow = true;
    }

    /** Nedorazil through the backend's action_no_show (no e-mail to the client). */
    noShow() {
        return this.run(async () => {
            const result = await callReception(this.orm, this.notification, "no_show_reservation", [
                this.detail.reservation_id,
            ]);
            if (result) {
                const who = this.detail.pet_name || this.detail.owner || "Klient";
                this.notification.add(`${who}: označeno jako nedorazil.`, { type: "success" });
                this.props.onChanged();
                this.props.close();
            } else {
                this.state.confirmNoShow = false;
                await this.load();
            }
        });
    }

    cancel() {
        return this.run(async () => {
            const result = await callReception(this.orm, this.notification, "cancel_reservation", [
                this.detail.reservation_id,
            ]);
            if (result) {
                const mail = result.email_sent ? " Klient dostane e-mail o zrušení." : "";
                this.notification.add(`Rezervace je zrušená.${mail}`, { type: "success" });
                this.props.onChanged();
                this.props.close();
            } else {
                this.state.confirmCancel = false;
                await this.load();
            }
        });
    }
}
