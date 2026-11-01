/** @odoo-module **/
/**
 * Request 1. 11. (Lucie): cancelling / rejecting a reservation asks first and, when the client gets
 * the cancellation e-mail, lets the clinic write a message (reason, another date…) that goes into it.
 * `onConfirm(message)` calls the server; an error is shown in the dialog, which stays open.
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { errorText } from "@elite_vet_reservation/move_dialog/move_dialog";

export class CancelDialog extends Component {
    static template = "elite_vet_reservation.CancelDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        question: String,
        confirmLabel: String,
        mailTo: { type: [String, Boolean], optional: true },
        onConfirm: Function,
    };

    setup() {
        this.state = useState({ message: "", busy: false, error: "" });
    }

    onMessage(ev) {
        this.state.message = ev.target.value;
    }

    async confirm() {
        this.state.busy = true;
        this.state.error = "";
        try {
            await this.props.onConfirm(this.props.mailTo ? this.state.message : null);
            this.props.close();
        } catch (error) {
            this.state.error = errorText(error);
        } finally {
            this.state.busy = false;
        }
    }
}
