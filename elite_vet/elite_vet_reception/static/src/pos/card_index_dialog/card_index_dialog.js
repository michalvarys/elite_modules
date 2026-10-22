/**
 * Kartotéka: a dialog above the till (the open order stays below it). One search, the owner with
 * the pets, forms to create / edit both, and the actions walk-in, book, customer of the order
 * and assigning the client to a reservation (opened from a Dnes row: that reservation; from the
 * toolbar: a pick from `reservations_to_assign`).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import {
    BOOKING_SCREEN,
    TODAY_SCREEN,
    callReception,
    errorMessage,
    shortDate,
} from "@elite_vet_reception/pos/reception_api";

const OWNER_FIELDS = ["name", "phone", "mobile", "email", "street", "city", "zip"];
const PET_FIELDS = ["name", "species", "breed", "sex", "birth_date", "chip", "note"];

function formValues(source, fields) {
    const values = {};
    for (const field of fields) {
        values[field] = (source && source[field]) || "";
    }
    return values;
}

export class CardIndexDialog extends Component {
    static template = "elite_vet_reception.CardIndexDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        // the reservation to assign a client to: {reservation_id, time, owner, partner_id, pet_id,
        // pet_name, ...} (today_data row); its client and pet are preloaded
        reservation: { type: Object, optional: true },
        // called after a change the caller shows (match, walk-in)
        onChanged: { type: Function, optional: true },
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            term: this.props.reservation?.owner || "",
            results: null,
            searching: false,
            data: null, // owner_data()
            petId: null,
            ownerForm: null, // {isNew, values, firstPet: {name, species}}
            petForm: null, // {petId, values}
            saving: false,
            doctors: [],
            walkInDoctorId: "",
            species: [],
            assign: null, // toolbar "Přiřadit k rezervaci…": {rows: reservations_to_assign() | null}
        });
        onWillStart(async () => {
            const [options, booking] = await Promise.all([
                callReception(this.orm, this.notification, "pet_options"),
                callReception(this.orm, this.notification, "booking_options"),
            ]);
            this.state.species = options?.species || [];
            this.state.doctors = booking?.doctors || [];
            const res = this.props.reservation;
            if (res?.partner_id) {
                await this.loadOwner(res.partner_id, res.pet_id || null);
                if (this.state.data) {
                    return;
                }
            }
            if (this.state.term.trim().length >= 2) {
                await this.search();
            }
        });
    }

    // ------------------------------------------------------------------ getters

    get title() {
        const res = this.props.reservation;
        return res ? `Kartotéka – rezervace ${res.time} (${res.owner || "bez jména"})` : "Kartotéka";
    }

    get owner() {
        return this.state.data?.owner || null;
    }

    get ownerPhones() {
        const owner = this.owner;
        return [owner?.mobile, owner?.phone].filter(Boolean).join(", ") || "–";
    }

    get ownerAddress() {
        const owner = this.owner;
        const town = [owner?.zip, owner?.city].filter(Boolean).join(" ");
        return [owner?.street, town].filter(Boolean).join(", ") || "–";
    }

    get pets() {
        return this.state.data?.pets || [];
    }

    get pet() {
        return this.pets.find((p) => p.id === this.state.petId) || null;
    }

    get canUsePet() {
        return Boolean(this.pet && !this.pet.deceased && !this.state.saving);
    }

    get editing() {
        return Boolean(this.state.ownerForm || this.state.petForm || this.state.assign);
    }

    formatAmount(amount) {
        return this.env.utils.formatCurrency(amount);
    }

    formatDate(isoDay) {
        return isoDay ? shortDate(isoDay) : "";
    }

    petLine(pet) {
        return [pet.species_label, pet.breed, pet.sex].filter(Boolean).join(", ");
    }

    // ------------------------------------------------------------------ search

    async search() {
        const term = this.state.term.trim();
        if (term.length < 2) {
            this.notification.add("Zadejte aspoň 2 znaky.", { type: "warning" });
            return;
        }
        this.state.searching = true;
        try {
            const results = await callReception(this.orm, this.notification, "card_search", [term]);
            if (results) {
                this.state.results = results;
                this.state.data = null;
                this.state.petId = null;
                this.state.ownerForm = null;
                this.state.petForm = null;
                this.state.assign = null;
            }
        } finally {
            this.state.searching = false;
        }
    }

    onSearchSubmit(ev) {
        ev.preventDefault();
        this.search();
    }

    resultKey(result) {
        return `${result.kind}-${result.id}`;
    }

    async openResult(result) {
        await this.loadOwner(result.partner_id, result.kind === "pet" ? result.id : null);
    }

    async loadOwner(partnerId, petId = null) {
        const data = await callReception(this.orm, this.notification, "owner_data", [partnerId]);
        if (data) {
            this.setData(data, petId);
        }
    }

    setData(data, petId = null) {
        this.state.data = data;
        const live = data.pets.filter((p) => !p.deceased);
        this.state.petId = petId || (live.length === 1 ? live[0].id : null);
    }

    backToResults() {
        this.state.data = null;
        this.state.petId = null;
        this.state.ownerForm = null;
        this.state.petForm = null;
        this.state.assign = null;
    }

    selectPet(pet) {
        this.state.petId = pet.id;
    }

    // ------------------------------------------------------------------ forms

    newOwner() {
        const res = this.props.reservation;
        this.state.petForm = null;
        this.state.assign = null;
        this.state.ownerForm = {
            isNew: true,
            values: formValues({ name: res?.owner || "" }, OWNER_FIELDS),
            firstPet: { name: res?.pet_name || "", species: "dog" },
        };
    }

    editOwner() {
        this.state.petForm = null;
        this.state.ownerForm = { isNew: false, values: formValues(this.owner, OWNER_FIELDS) };
    }

    newPet() {
        this.state.ownerForm = null;
        this.state.petForm = { petId: null, values: formValues({ species: "dog" }, PET_FIELDS) };
    }

    editPet() {
        if (!this.pet) {
            return;
        }
        this.state.ownerForm = null;
        this.state.petForm = { petId: this.pet.id, values: formValues(this.pet, PET_FIELDS) };
    }

    cancelForm() {
        this.state.ownerForm = null;
        this.state.petForm = null;
    }

    async saveOwner(ev) {
        ev?.preventDefault();
        const form = this.state.ownerForm;
        if (!form.values.name.trim()) {
            this.notification.add("Vyplňte jméno majitele.", { type: "warning" });
            return;
        }
        if (form.isNew && form.firstPet.name.trim() && !form.firstPet.species) {
            this.notification.add("Vyberte druh zvířete.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const args = form.isNew ? [form.values] : [form.values, this.owner.id];
            let data = await callReception(this.orm, this.notification, "save_owner", args);
            if (!data) {
                return;
            }
            let petId = this.state.petId;
            if (form.isNew && form.firstPet.name.trim()) {
                const withPet = await callReception(this.orm, this.notification, "save_pet", [
                    data.owner.id,
                    { name: form.firstPet.name, species: form.firstPet.species },
                ]);
                if (withPet) {
                    data = withPet;
                    petId = withPet.pets.find((p) => p.name === form.firstPet.name.trim())?.id || null;
                }
            }
            this.state.ownerForm = null;
            this.setData(data, petId);
            this.notification.add(form.isNew ? "Klient je založený." : "Klient je uložený.", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async savePet(ev) {
        ev?.preventDefault();
        const form = this.state.petForm;
        if (!form.values.name.trim()) {
            this.notification.add("Vyplňte jméno zvířete.", { type: "warning" });
            return;
        }
        if (!form.values.species) {
            this.notification.add("Vyberte druh zvířete.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const args = [this.owner.id, form.values];
            if (form.petId) {
                args.push(form.petId);
            }
            const data = await callReception(this.orm, this.notification, "save_pet", args);
            if (!data) {
                return;
            }
            const before = new Set(this.pets.map((p) => p.id));
            const petId = form.petId || data.pets.find((p) => !before.has(p.id))?.id || null;
            this.state.petForm = null;
            this.setData(data, petId);
            this.notification.add("Zvíře je uložené.", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    // ------------------------------------------------------------------ actions

    async walkIn() {
        if (!this.canUsePet) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "walk_in", [
                this.pet.id,
                Number(this.state.walkInDoctorId) || false,
                this.pos.get_cashier()?.name || null,
            ]);
            if (result) {
                this.notification.add(`${result.pet_name} je v čekárně.`, { type: "success" });
                this.props.onChanged?.();
                this.props.close();
                this.pos.showScreen(TODAY_SCREEN);
            }
        } finally {
            this.state.saving = false;
        }
    }

    book() {
        if (!this.canUsePet) {
            return;
        }
        const pet = { id: this.pet.id, name: this.pet.name, owner: this.owner.name, partner_id: this.owner.id };
        this.props.close();
        this.pos.showScreen(BOOKING_SCREEN, { pet });
    }

    async selectForOrder() {
        if (!this.owner) {
            return;
        }
        const id = this.owner.id;
        let partner = this.pos.models["res.partner"].get(id);
        if (!partner) {
            try {
                partner = (await this.pos.data.read("res.partner", [id]))[0];
            } catch (error) {
                this.notification.add(errorMessage(error), { type: "danger" });
                return;
            }
        }
        if (!partner) {
            this.notification.add("Klienta se nepodařilo načíst do pokladny.", { type: "danger" });
            return;
        }
        let order = this.pos.get_order();
        const current = order?.get_partner();
        // an order with lines of another client (e.g. a loaded bill) is never handed to this one;
        // items rung up without a customer stay and get this client
        if (!order || order.finalized || (order.get_orderlines().length && current && current.id !== partner.id)) {
            order = this.pos.add_new_order();
        }
        order.set_partner(partner);
        this.notification.add(`Zákazník účtu: ${partner.name}`, { type: "success" });
        this.props.close();
        this.pos.showScreen("ProductScreen");
    }

    async assignTo(reservation) {
        if (!reservation || !this.canUsePet) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "match_reservation", [
                reservation.reservation_id,
                this.owner.id,
                this.pet.id,
            ]);
            if (result) {
                const when = [reservation.date_label, result.time].filter(Boolean).join(" ");
                this.notification.add(
                    `Klient je přiřazený k rezervaci ${when}: ${result.pet_name} (${result.owner}).`,
                    { type: "success" }
                );
                this.props.onChanged?.();
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }

    /** Reservation mode: the reservation the dialog was opened for. */
    matchReservation() {
        return this.assignTo(this.props.reservation);
    }

    /** Toolbar mode: list today's and the next 7 days' reservations to pick from. */
    async openAssign() {
        if (!this.canUsePet) {
            return;
        }
        this.state.assign = { rows: null };
        const rows = await callReception(this.orm, this.notification, "reservations_to_assign");
        if (!this.state.assign) {
            return; // closed meanwhile
        }
        if (rows) {
            this.state.assign.rows = rows;
        } else {
            this.state.assign = null;
        }
    }

    closeAssign() {
        this.state.assign = null;
    }

    assignLine(row) {
        const client = row.needs_match
            ? `${[row.pet_name, row.owner || "bez jména"].filter(Boolean).join(", ")} · nespárováno`
            : `${row.pet_name || "bez zvířete"} (${row.owner || "bez jména"})`;
        return [client, row.procedure, row.doctor].filter(Boolean).join(" · ");
    }
}
