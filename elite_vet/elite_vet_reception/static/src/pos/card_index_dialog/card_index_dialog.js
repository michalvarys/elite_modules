/**
 * Kartotéka: a dialog above the till (the open order stays below it). One search, the owner with
 * the pets and forms to create / edit both. The dialog has one task given by the place it is
 * opened from (`mode`), stated in its title, and exactly one primary action for it:
 * - `browse` (navbar Kartotéka…): search, view, create and edit only - no assignment;
 * - `booking` (Objednat, field Klient a zvíře): Vybrat → `onSelect(pet)` fills the booking form;
 * - `order` (Pokladna, button Klient): Vybrat k účtu → customer of the open order;
 * - `reservation` (Dnes Klient… / Spárovat, board detail Klient…): Přiřadit k rezervaci;
 * - `walk_in` (Dnes + Bez objednání): Přijmout with a doctor (any / a specific one) and optionally a room;
 * - `winvet` (task 30: Dnes / screen Ordinace Spárovat… of a WinVet appointment without a pet):
 *   Přiřadit k objednávce (pair_winvet), Zrušit spárování when it is paired already.
 * The dialog runs in the POS and in the backend (screen Ordinace): the POS service is optional and
 * used only by the till modes (order, walk_in cashier).
 * Task 31: Nový klient has the full pet form (template CardIndexPetFields, the same as + Nové
 * zvíře, without Uhynulý); the client and the pet are saved in one call (save_owner with pet_vals).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { callReception, errorMessage, shortDate } from "@elite_vet_reception/pos/reception_api";

const OWNER_FIELDS = ["name", "phone", "mobile", "email", "street", "city", "zip"];
// Task 22: every pet field of the form as text (deceased and alerts are kept apart)
const PET_FIELDS = [
    "name", "species", "species_other", "breed", "sex", "birth_date", "chip",
    "birth_year", "color", "weight", "tattoo", "passport", "next_vaccination", "next_deworming",
    "important_note", "note", "death_date",
];
// fields of the collapsible section Další údaje (open when any of them has a value)
const PET_MORE_FIELDS = [
    "birth_year", "color", "weight", "tattoo", "passport", "next_vaccination", "next_deworming",
    "important_note", "note",
];

export const CARD_INDEX_MODES = ["browse", "booking", "order", "reservation", "walk_in", "winvet"];

const MODE_TITLES = {
    browse: "Kartotéka",
    booking: "Vybrat klienta a zvíře pro objednání",
    order: "Klient k účtu v pokladně",
    walk_in: "Přijmout bez objednání",
    winvet: "Spárovat s objednávkou z WinVetu",
};

const MODE_HINTS = {
    browse: "Hledání, prohlížení, založení a úprava klientů a zvířat.",
    booking: "Najděte nebo založte klienta, vyberte zvíře a stiskněte Vybrat – zapíše se do formuláře Objednat.",
    order: "Najděte nebo založte klienta a stiskněte Vybrat k účtu – bude zákazníkem rozdělaného účtu.",
    reservation: "Najděte nebo založte klienta, vyberte zvíře a stiskněte Přiřadit k rezervaci.",
    walk_in: "Najděte nebo založte klienta, vyberte zvíře a lékařku a stiskněte Přijmout – půjde do čekárny.",
    winvet: "Najděte nebo založte klienta, vyberte zvíře a stiskněte Přiřadit k objednávce. Uloží se jen v Odoo, WinVet se nemění.",
};

function formValues(source, fields) {
    const values = {};
    for (const field of fields) {
        values[field] = (source && source[field]) || "";
    }
    return values;
}

/** Pet form values as text: weight with a decimal comma, years and dates as typed. */
function petFormValues(pet) {
    const values = formValues(pet, PET_FIELDS);
    if (pet?.weight) {
        values.weight = String(pet.weight).replace(".", ",");
    }
    if (pet?.birth_year) {
        values.birth_year = String(pet.birth_year);
    }
    return values;
}

/** State of the pet form (Task 22; reused by Nový klient, task 31). */
function petFormState(pet, { petId = null, alerts = [], deceased = false, showMore = false } = {}) {
    return { petId, values: petFormValues(pet), alerts, deceased, wasDeceased: deceased, showMore, error: null };
}

/** True when the pet part of Nový klient has anything besides the preset Druh. */
function petFormTouched(pf) {
    return Boolean(
        pf.alerts.length || PET_FIELDS.some((f) => f !== "species" && f !== "death_date" && String(pf.values[f]).trim())
    );
}

/** "12,5 kg" */
export function weightLabel(weight) {
    return weight ? `${String(Math.round(weight * 100) / 100).replace(".", ",")} kg` : "";
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
        // winvet mode: the WinVet row {winvet_event_id, time, winvet_title, search_hint, pet_id,
        // partner_id, paired_manually} (today_data / room_board item)
        winvet: { type: Object, optional: true },
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
        // POS only (the backend screen Ordinace opens the dialog in the winvet mode)
        this.pos = this.env.services.pos || null;
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            term: this.initialTerm(),
            results: null,
            searching: false,
            data: null, // owner_data()
            petId: null,
            ownerForm: null, // {isNew, values, pet (a petForm, new owner only), error}
            petForm: null, // {petId, values, alerts: [{key, id, kind, note}], deceased, wasDeceased, showMore, error}
            saving: false,
            doctors: [],
            walkInDoctorId: "",
            rooms: [],
            walkInRoomId: "", // optional room of the walk-in (task 15); empty = Nepřiřazení
            walkInNote: "", // optional internal note of the reception for the room
            species: [],
            alertKinds: [],
        });
        this.alertKey = 0;
        onWillStart(async () => {
            const walkIn = this.mode === "walk_in";
            const [options, booking] = await Promise.all([
                callReception(this.orm, this.notification, "pet_options"),
                walkIn ? callReception(this.orm, this.notification, "booking_options") : null,
            ]);
            this.state.species = options?.species || [];
            this.state.alertKinds = options?.alert_kinds || [];
            this.state.doctors = booking?.doctors || [];
            this.state.rooms = booking?.rooms || [];
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
                // WinVet text "Jméno Příjmení": nothing for both words -> the first one alone
                const words = this.state.term.trim().split(/\s+/);
                if (this.mode === "winvet" && !this.state.results?.length && words.length > 1) {
                    this.state.term = words[0];
                    if (words[0].length >= 2) {
                        await this.search();
                    }
                }
            }
        });
    }

    // ------------------------------------------------------------------ getters

    get mode() {
        return this.props.mode;
    }

    initialTerm() {
        if (this.props.mode === "reservation") {
            return this.props.reservation?.owner || "";
        }
        if (this.props.mode === "winvet") {
            return this.props.winvet?.search_hint || "";
        }
        return "";
    }

    get title() {
        if (this.mode === "reservation") {
            const res = this.props.reservation || {};
            return ["Klient k rezervaci", res.time, res.procedure].filter(Boolean).join(" ");
        }
        if (this.mode === "winvet") {
            return [MODE_TITLES.winvet, this.props.winvet?.time].filter(Boolean).join(" ");
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
        if (this.mode === "winvet") {
            return this.props.winvet?.pet_id ? this.props.winvet : null;
        }
        if (this.props.client) {
            return this.props.client;
        }
        if (this.mode === "order" && this.pos) {
            const partner = this.pos.get_order()?.get_partner();
            return partner ? { partner_id: partner.id } : null;
        }
        return null;
    }

    /** The primary action needs a selected (live) pet; Vybrat k účtu needs the owner only. */
    get needsPet() {
        return ["booking", "reservation", "walk_in", "winvet"].includes(this.mode);
    }

    get owner() {
        return this.state.data?.owner || null;
    }

    /** Tooltip of the badge Nedorazil N×: one line per no-show (newest first). */
    get noShowTitle() {
        const ns = this.state.data?.no_shows;
        if (!ns?.count) {
            return "";
        }
        const lines = ns.items.map((i) => [i.date_label, i.procedure, i.pet].filter(Boolean).join(" · "));
        return `${ns.text}\n${lines.join("\n")}`;
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
        if (this.env.utils?.formatCurrency) {
            return this.env.utils.formatCurrency(amount);
        }
        // backend (screen Ordinace): no POS currency helper - the clinic bills in CZK
        return new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "CZK" }).format(amount || 0);
    }

    formatDate(isoDay) {
        return isoDay ? shortDate(isoDay) : "";
    }

    petLine(pet) {
        return [pet.species_label, pet.breed, pet.sex].filter(Boolean).join(", ");
    }

    /** Second line of a pet in the owner card: birth, chip, weight, vaccination, deworming. */
    petDetails(pet) {
        const birth = pet.birth_date ? this.formatDate(pet.birth_date) : pet.birth_year || "";
        return [
            birth && `nar. ${birth}`,
            pet.chip && `čip ${pet.chip}`,
            pet.weight && weightLabel(pet.weight),
            pet.next_vaccination && `očkování ${this.formatDate(pet.next_vaccination)}`,
            pet.next_deworming && `odčervení ${this.formatDate(pet.next_deworming)}`,
            pet.deceased && pet.death_date && `úhyn ${this.formatDate(pet.death_date)}`,
        ]
            .filter(Boolean)
            .join(" · ");
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
        // winvet: the name as the search was prefilled (from the WinVet text, editable)
        const name = res?.owner || (this.mode === "winvet" ? this.state.term.trim() : "");
        this.state.petForm = null;
        this.state.ownerForm = {
            isNew: true,
            values: formValues({ name }, OWNER_FIELDS),
            // task 31: the full pet form of task 22 (Další údaje closed, no Uhynulý)
            pet: petFormState({ name: res?.pet_name || "", species: "dog" }),
            error: null,
        };
    }

    editOwner() {
        this.state.petForm = null;
        this.state.ownerForm = { isNew: false, values: formValues(this.owner, OWNER_FIELDS), error: null };
    }

    newPet() {
        this.state.ownerForm = null;
        this.state.petForm = petFormState({ species: "dog" }); // Další údaje closed on a new pet
    }

    editPet() {
        if (!this.pet) {
            return;
        }
        const pet = this.pet;
        const values = petFormValues(pet);
        this.state.ownerForm = null;
        this.state.petForm = petFormState(pet, {
            petId: pet.id,
            alerts: (pet.alert_list || []).map((a) => ({
                key: ++this.alertKey,
                id: a.id,
                kind: a.kind,
                note: a.note || "",
            })),
            deceased: pet.deceased,
            showMore: PET_MORE_FIELDS.some((f) => values[f]),
        });
    }

    // the pet fields (template CardIndexPetFields) work on the form they are given: the pet form
    // or the pet part of Nový klient
    toggleMore(pf) {
        pf.showMore = !pf.showMore;
    }

    addAlert(pf) {
        pf.alerts.push({
            key: ++this.alertKey,
            id: null,
            kind: this.state.alertKinds[0]?.value || "other",
            note: "",
        });
    }

    removeAlert(pf, alert) {
        pf.alerts.splice(pf.alerts.indexOf(alert), 1);
    }

    /** Values of save_pet from a pet form; Uhynulý only when editing (never on registration). */
    petVals(pf) {
        const vals = {
            ...pf.values,
            alerts: pf.alerts.map((a) => ({ id: a.id || false, kind: a.kind, note: a.note })),
        };
        if (pf.petId) {
            vals.deceased = pf.deceased;
        } else {
            delete vals.death_date;
        }
        return vals;
    }

    /** Nový klient with a filled pet: the pet goes with the client (one save). */
    get ownerFormHasPet() {
        const form = this.state.ownerForm;
        return Boolean(form?.isNew && form.pet.values.name.trim());
    }

    /** winvet mode, Nový klient with a pet: the appointment is paired right after the save. */
    get saveOwnerPairs() {
        return this.mode === "winvet" && this.ownerFormHasPet;
    }

    get saveOwnerLabel() {
        return this.saveOwnerPairs ? "Uložit a přiřadit k objednávce" : "Uložit klienta";
    }

    /** Resolves true when the user confirms marking the pet as deceased. */
    confirmDeceased(name) {
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    title: "Uhynulé zvíře",
                    body: `Označit ${name} jako uhynulé? Uhynulé zvíře nejde objednat ani přijmout.`,
                    confirmLabel: "Označit jako uhynulé",
                    cancelLabel: "Zrušit",
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) }
            );
        });
    }

    cancelForm() {
        this.state.ownerForm = null;
        this.state.petForm = null;
    }

    /** A warning shown in the form (and as a notification). */
    formError(form, message) {
        form.error = message;
        this.notification.add(message, { type: "warning" });
    }

    async saveOwner(ev) {
        ev?.preventDefault();
        const form = this.state.ownerForm;
        form.error = null;
        if (!form.values.name.trim()) {
            this.formError(form, "Vyplňte jméno majitele.");
            return;
        }
        const withPet = this.ownerFormHasPet;
        if (form.isNew && !withPet && petFormTouched(form.pet)) {
            this.formError(form, "Vyplňte jméno zvířete, nebo údaje zvířete smažte.");
            return;
        }
        if (withPet && !form.pet.values.species) {
            this.formError(form, "Vyberte druh zvířete.");
            return;
        }
        const pairs = this.saveOwnerPairs;
        this.state.saving = true;
        let data;
        try {
            // task 31: a new client with a pet in one call (nothing is created when the pet is refused)
            const args = form.isNew ? [form.values, false] : [form.values, this.owner.id];
            if (withPet) {
                args.push(this.petVals(form.pet));
            }
            data = await callReception(this.orm, this.notification, "save_owner", args, { rethrow: true });
        } catch (error) {
            form.error = errorMessage(error); // the form stays open with everything typed
            return;
        } finally {
            this.state.saving = false;
        }
        this.state.ownerForm = null;
        this.setData(data, withPet ? data.new_pet_id : this.state.petId);
        this.notification.add(form.isNew ? "Klient je založený." : "Klient je uložený.", { type: "success" });
        if (pairs && this.pet) {
            await this.pairWinvet(); // one click: save and pair (on failure the new card stays open)
        }
    }

    async savePet(ev) {
        ev?.preventDefault();
        const form = this.state.petForm;
        form.error = null;
        if (!form.values.name.trim()) {
            this.formError(form, "Vyplňte jméno zvířete.");
            return;
        }
        if (!form.values.species) {
            this.formError(form, "Vyberte druh zvířete.");
            return;
        }
        if (form.petId && form.deceased && !form.wasDeceased && !(await this.confirmDeceased(form.values.name.trim()))) {
            return;
        }
        const vals = this.petVals(form);
        this.state.saving = true;
        try {
            const args = [this.owner.id, vals];
            if (form.petId) {
                args.push(form.petId);
            }
            let data;
            try {
                data = await callReception(this.orm, this.notification, "save_pet", args, { rethrow: true });
            } catch (error) {
                form.error = errorMessage(error);
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
                this.pos?.get_cashier()?.name || null,
                Number(this.state.walkInRoomId) || false,
                this.state.walkInNote.trim() || null,
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
        if (!this.owner || !this.pos) {
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

    /** winvet: Přiřadit k objednávce - the pet of a WinVet appointment without a patient (task 30). */
    async pairWinvet() {
        const row = this.props.winvet;
        if (!row || !this.canUsePet) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "pair_winvet", [
                row.winvet_event_id,
                this.owner.id,
                this.pet.id,
            ]);
            if (result) {
                this.notification.add(
                    `Objednávka ${result.time} je spárovaná: ${result.pet_name} (${result.owner}).`,
                    { type: "success" }
                );
                this.props.onChanged?.();
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }

    /** winvet: Zrušit spárování - the appointment is without a pet again. */
    async unpairWinvet() {
        const row = this.props.winvet;
        if (!row?.paired_manually) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await callReception(this.orm, this.notification, "unpair_winvet", [row.winvet_event_id]);
            if (result) {
                this.notification.add("Spárování je zrušené.", { type: "success" });
                this.props.onChanged?.();
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }
}
