/** Dnes: arriving reservations, waiting room / consulting rooms and bills to pay. */
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
import { NoteDialog } from "@elite_vet_reception/pos/note_dialog/note_dialog";
import {
    TODAY_SCREEN,
    callReception,
    clinicToday,
    dayLabel,
    errorMessage,
    shiftDay,
} from "@elite_vet_reception/pos/reception_api";

const BUS_MESSAGE = "elite_vet_reservation/changed";
const POLL_MS = 30000;

export class ReceptionTodayScreen extends Component {
    static template = "elite_vet_reception.TodayScreen";
    static props = {};
    static storeOnOrder = false;

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            day: clinicToday(),
            data: null,
            error: null, // message when the last load failed and there is nothing to show
            followToday: true, // showing "today": roll over to the next day at midnight
            loading: false,
            busy: {}, // key -> true while an action of the row runs
        });
        this.onBusChange = () => this.load();
        onWillStart(() => this.load());
        onMounted(() => {
            // as the product screen does: a new session asks for the opening cash first
            this.pos.openOpeningControl();
            this.pos.bus?.subscribe(BUS_MESSAGE, this.onBusChange);
            this.timer = setInterval(() => {
                if (!document.hidden) {
                    this.load();
                }
            }, POLL_MS);
        });
        onWillUnmount(() => {
            this.pos.bus?.unsubscribe(BUS_MESSAGE, this.onBusChange);
            clearInterval(this.timer);
        });
    }

    get isToday() {
        return this.state.day === clinicToday();
    }

    get dayTitle() {
        return this.isToday ? `Dnes, ${dayLabel(this.state.day)}` : dayLabel(this.state.day);
    }

    get cashierName() {
        return this.pos.get_cashier()?.name || null;
    }

    async load() {
        if (this.state.followToday && this.state.day !== clinicToday()) {
            this.state.day = clinicToday(); // midnight passed while Dnes was open
            this.state.data = null;
        }
        const day = this.state.day;
        this.state.loading = true;
        try {
            const data = await this.orm.call("elite.vet.reception", "today_data", [day]);
            // a slow answer for a day the user already left must not overwrite the view
            if (day === this.state.day) {
                this.state.data = data;
                this.state.error = null;
                this.failing = false;
            }
        } catch (error) {
            const firstFailure = !this.failing;
            if (day === this.state.day) {
                if (this.state.data) {
                    // repeated poll / bus failures: tell once per failure streak
                    if (firstFailure) {
                        this.notification.add(errorMessage(error), { type: "danger" });
                    }
                } else {
                    this.state.error = errorMessage(error);
                }
            }
            this.failing = true;
        } finally {
            this.state.loading = false;
        }
    }

    changeDay(delta) {
        this.state.day = delta ? shiftDay(this.state.day, delta) : clinicToday();
        this.state.followToday = this.state.day === clinicToday();
        this.state.data = null;
        this.state.error = null;
        this.load();
    }

    formatAmount(amount) {
        return this.env.utils.formatCurrency(amount);
    }

    /** Task 27: the visit report for the owner (PDF without the internal notes) in a new tab. */
    printReport(row) {
        window.open(`/report/pdf/elite_vet_clinic.report_visit_document/${row.record_id}`, "_blank");
    }

    async run(key, action) {
        if (this.state.busy[key]) {
            return;
        }
        this.state.busy[key] = true;
        try {
            return await action();
        } finally {
            delete this.state.busy[key];
        }
    }

    /** Přijmout: a small dialog with an optional internal note for the room (Enter = Přijmout). */
    checkIn(row) {
        const busyKey = `in-${row.key || row.reservation_id}`;
        if (this.state.busy[busyKey]) {
            return;
        }
        // WinVet calendar entry (read-only): check_in_winvet creates / reuses the visit record
        const [method, id] = row.winvet_event_id
            ? ["check_in_winvet", row.winvet_event_id]
            : ["check_in", row.reservation_id];
        this.dialog.add(NoteDialog, {
            title: `Přijmout: ${[row.pet_name, row.owner].filter(Boolean).join(" · ")}`,
            label: "Interní poznámka pro ordinaci (nepovinné)",
            hint: "Uvidí ji sestra a lékařka v ordinaci, klient nikde. Enter = Přijmout.",
            confirmLabel: "Přijmout do čekárny",
            onConfirm: (note) =>
                this.run(busyKey, async () => {
                    const result = await callReception(this.orm, this.notification, method, [
                        id,
                        this.cashierName,
                        note || null,
                    ]);
                    if (result) {
                        this.notification.add(`${result.pet_name} je v čekárně.`, { type: "success" });
                    }
                    await this.load();
                    return Boolean(result);
                }),
        });
    }

    /** Poznámka: edit (or clear) the reception note of a waiting / in-room visit. */
    editNote(row) {
        this.dialog.add(NoteDialog, {
            title: `Poznámka recepce: ${row.pet_name}`,
            label: "Interní poznámka pro ordinaci",
            hint: "Prázdné pole poznámku smaže. Klient ji nikde nevidí.",
            value: row.reception_note || "",
            confirmLabel: "Uložit",
            onConfirm: (note) =>
                this.run(`note-${row.record_id}`, async () => {
                    const result = await callReception(this.orm, this.notification, "set_reception_note", [
                        row.record_id,
                        note || false,
                    ]);
                    await this.load();
                    return Boolean(result);
                }),
        });
    }

    /** Kartotéka for the reservation: its client and pet preloaded, "Přiřadit k rezervaci". */
    openClient(row) {
        this.dialog.add(CardIndexDialog, {
            mode: "reservation",
            reservation: row,
            onChanged: () => this.load(),
        });
    }

    /** + Bez objednání: Kartotéka in the walk-in mode, "Přijmout" with a doctor. */
    openWalkIn() {
        this.dialog.add(CardIndexDialog, {
            mode: "walk_in",
            onChanged: () => this.load(),
        });
    }

    /** Zaplatit; with a note of the room the reception reads it first (Pokračovat k platbě). */
    pay(row) {
        if (row.room_note) {
            this.dialog.add(NoteDialog, {
                title: `Poznámka z ordinace: ${row.pet_name}`,
                value: row.room_note,
                readonly: true,
                hint: "Interní poznámka pro recepci – na účtence ani faktuře nebude.",
                confirmLabel: "Pokračovat k platbě",
                cancelLabel: "Zpět",
                onConfirm: async () => {
                    this.payBill(row);
                    return true;
                },
            });
            return;
        }
        return this.payBill(row);
    }

    payBill(row) {
        return this.run(`pay-${row.record_id}`, async () => {
            try {
                await this.pos.payReceptionBill(row.sale_order_id);
            } catch (error) {
                this.notification.add(errorMessage(error), { type: "danger" });
            }
        });
    }
}

registry.category("pos_screens").add(TODAY_SCREEN, ReceptionTodayScreen);
