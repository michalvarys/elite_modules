/**
 * Small dialog with one internal note (request 25. 10.): Přijmout with an optional note for the
 * room (Dnes, the board), editing the reception note of an open visit, reading the note of the
 * room before Zaplatit. Enter confirms, Shift+Enter is a new line, Esc closes.
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class NoteDialog extends Component {
    static template = "elite_vet_reception.NoteDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        label: { type: String, optional: true }, // label of the field (editable dialog)
        hint: { type: String, optional: true }, // small text under the field
        value: { type: String, optional: true },
        readonly: { type: Boolean, optional: true }, // show the note only (Zaplatit)
        confirmLabel: String,
        cancelLabel: { type: String, optional: true },
        // async (text) => truthy to close the dialog; a falsy result keeps it open
        onConfirm: Function,
    };
    static defaultProps = { value: "", cancelLabel: "Zrušit" };

    setup() {
        this.state = useState({ text: this.props.value || "", busy: false });
        this.textRef = useRef("text");
        this.confirmRef = useRef("confirm");
        onMounted(() => {
            const el = this.props.readonly ? this.confirmRef.el : this.textRef.el;
            el?.focus();
            if (!this.props.readonly && el) {
                el.setSelectionRange(el.value.length, el.value.length);
            }
        });
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.confirm();
        }
    }

    async confirm() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            if (await this.props.onConfirm(this.state.text.trim())) {
                this.props.close();
            }
        } finally {
            this.state.busy = false;
        }
    }
}
