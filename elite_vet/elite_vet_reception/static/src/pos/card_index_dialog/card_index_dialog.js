/**
 * Kartotéka: a dialog above the till (the open order stays below it). One search, the owner with
 * the pets and forms to create / edit both. The dialog has one task given by the place it is
 * opened from (`mode`), stated in its title, and exactly one primary action for it:
 * - `browse` (navbar Kartotéka…): search, view, create and edit only - no assignment;
 * - `booking` (Objednat, field Klient a zvíře): Vybrat → `onSelect(pet)` fills the booking form;
 * - `order` (Pokladna, button Klient): Vybrat k účtu → customer of the open order;
 * - `reservation` (Dnes Klient… / Spárovat, board detail Klient…): Přiřadit k rezervaci;
 * - `walk_in` (Dnes + Bez objednání): Přijmout with a doctor (any / a specific one).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { callReception, errorMessage, shortDate } from "@elite_vet_reception/pos/reception_api";

const OWNER_FIELDS = ["name", "phone", "mobile", "email", "street", "city", "zip"];
const PET_FIELDS = ["name", "species", "breed", "sex", "birth_date", "chip", "note"];

export const CARD_INDEX_MODES = ["browse", "booking", "order", "reservation", "walk_in"];

const MODE_TITLES = {
    browse: "Kartotéka",
    booking: "Vybrat klienta a zvíře pro objednání",
    order: "Klient k účtu v pokladně",
    walk_in: "Přijmout bez objednání",
};

const MODE_HINTS = {
    browse: "Hledání, prohlížení, založení a úprava klientů a zvířat.",
    booking: "Najděte nebo založte klienta, vyberte zvíře a stiskněte Vybrat – zapíše se do formuláře Objednat.",
    order: "Najděte nebo založte klienta a stiskněte Vybrat k účtu – bude zákazníkem rozdělaného účtu.",
    reservation: "Najděte nebo založte klienta, vyberte zvíře a stiskněte Přiřadit k rezervaci.",
    walk_in: "Najděte nebo založte klienta, vyberte zvíře a lékařku a stiskněte Přijmout – půjde do čekárny.",
};

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
        mode: { validate: (m) => CARD_INDEX_MODES.includes(m), optional: true },
        // reservation mode: {reservation_id, time, procedure, owner, partner_id, pet_id, pet_name}
        // (today_data row / board detail); its client and pet are preloaded
        reservation: { type: Object, optional: true },
        // booking / order mode: the client shown first {partner_id, pet_id}
        client: { type: Object, optional: true },
        // booking mode: (pet: {id, name, owner, partner_id}) => void
        onSelect: { type: Function, optional: true },
        // form opened first: "new_owner" (Objednat + Nový klient) or "new_pet" (for `client`,
        // an owner without a live pet picked in the inline search of Objednat)
        start: { validate: (s) => ["new_owner", "new_pet"].includes(s), optional: true },
        // called after a change the caller shows (match, walk-in)
        onChanged: { type: Function, optional: true },
    };
    static defaultProps = { mode: "browse" };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            term: (this.props.mode === "reservation" && this.props.reservation?.owner) || "",
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
        });
        onWillStart(async () => {
            const walkIn = this.mode === "walk_in";
            const [options, booking] = await Promise.all([
                callReception(this.orm, this.notification, "pet_options"),
                walkIn ? callReception(this.orm, this.notification, "booking_options") : null,
            ]);
            this.state.species = options?.species || [];
            this.state.doctors = booking?.doctors || [];
            if (this.props.start === "new_owner") {
                this.newOwner();
                return;
            }
            const preset = this.preset;
            if (preset?.partner_id) {
                await this.loadOwner(preset.partner_id, preset.pet_id || null);
                if (this.state.data) {
                    if (this.props.start === "new_pet") {
                        this.newPet();
                    }
                    return;
                }
            }
            if (this.state.term.trim().length >= 2) {
                await this.search();
            }
        });
    }

    // ------------------------------------------------------------------ getters

    get mode() {
        return this.props.mode;
    }

    get title() {
        if (this.mode === "reservation") {
            const res = this.props.reservation || {};
            return ["Klient k rezervaci", res.time, res.procedure].filter(Boolean).join(" ");
        }
        return MODE_TITLES[this.mode];
    }

    get hint() {
        return MODE_HINTS[this.mode];
    }

    /** The client shown when the dialog opens. */
    get preset() {
        if (this.mode === "reservation") {
            return this.props.reservation;
        }
        if (this.props.client) {
            return this.props.client;
        }
        if (this.mode === "order") {
            const partner = this.pos.get_order()?.get_partner();
            return partner ? { partner_id: partner.id } : null;
        }
        return null;
    }

    /** The primary action needs a selected (live) pet; Vybrat k účtu needs the owner only. */
    get needsPet() {
        return ["booking", "reservation", "walk_in"].includes(this.mode);
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
        return Boolean(this.state.ownerForm || this.state.petForm);
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
    }

    selectPet(pet) {
        this.state.petId = pet.id;
    }

    // ------------------------------------------------------------------ forms

    newOwner() {
        const res = this.mode === "reservation" ? this.props.reservation : null;
        this.state.petForm = null;
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

    // ------------------------------------------------------------------ primary actions

    /** walk_in: Přijmout - the pet goes to the waiting room (Dnes reloads). */
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
            }
        } finally {
            this.state.saving = false;
        }
    }

    /** booking: Vybrat - the owner and pet go into the Objednat form. */
    pickForBooking() {
        if (!this.canUsePet) {
            return;
        }
        this.props.onSelect?.({
            id: this.pet.id,
            name: this.pet.name,
            owner: this.owner.name,
            partner_id: this.owner.id,
        });
        this.props.close();
    }

    /** order: Vybrat k účtu - customer of the open order (Task 5 rules). */
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
        let newOrder = false;
        // an order with lines of another client (e.g. a loaded bill) is never handed to this one;
        // items rung up without a customer stay and get this client
        if (!order || order.finalized || (order.get_orderlines().length && current && current.id !== partner.id)) {
            order = this.pos.add_new_order();
            newOrder = true;
        }
        order.set_partner(partner);
        this.notification.add(`Zákazník účtu: ${partner.name}`, { type: "success" });
        this.props.close();
        // opened from the payment screen (Zákazník, invoice) for the same order: payment goes on
        if (newOrder || this.pos.mainScreen.component?.name !== "PaymentScreen") {
            this.pos.showScreen("ProductScreen");
        }
    }

    /** reservation: Přiřadit k rezervaci - the client and pet of the reservation. */
    async matchReservation() {
        const reservation = this.props.reservation;
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
                this.notification.add(
                    `Klient je přiřazený k rezervaci ${result.time}: ${result.pet_name} (${result.owner}).`,
                    { type: "success" }
                );
                this.props.onChanged?.();
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }
}
