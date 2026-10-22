/** Dnes: arriving reservations, waiting room / consulting rooms and bills to pay. */
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { CardIndexDialog } from "@elite_vet_reception/pos/card_index_dialog/card_index_dialog";
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
        const day = this.state.day;
        this.state.loading = true;
        try {
            const data = await callReception(this.orm, this.notification, "today_data", [day]);
            // a slow answer for a day the user already left must not overwrite the view
            if (data && day === this.state.day) {
                this.state.data = data;
            }
        } finally {
            this.state.loading = false;
        }
    }

    changeDay(delta) {
        this.state.day = delta ? shiftDay(this.state.day, delta) : clinicToday();
        this.state.data = null;
        this.load();
    }

    formatAmount(amount) {
        return this.env.utils.formatCurrency(amount);
    }

    async run(key, action) {
        if (this.state.busy[key]) {
            return;
        }
        this.state.busy[key] = true;
        try {
            await action();
        } finally {
            delete this.state.busy[key];
        }
    }

    checkIn(row) {
        return this.run(`in-${row.reservation_id}`, async () => {
            const result = await callReception(this.orm, this.notification, "check_in", [
                row.reservation_id,
                this.cashierName,
            ]);
            if (result) {
                this.notification.add(`${result.pet_name} je v čekárně.`, { type: "success" });
            }
            await this.load();
        });
    }

    openMatch(row) {
        this.dialog.add(CardIndexDialog, {
            reservation: row,
            onChanged: () => this.load(),
        });
    }

    pay(row) {
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
