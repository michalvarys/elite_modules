""""New reservation" wizard for the reception desk.

Four steps in a single dialog (the `step` field); buttons return an action for
the same wizard so the dialog stays open. Free times come from the same engine
as the website (elite.vet.availability.slots), only without the minimum lead
time - reception may book for today as well. _check_overlap on save has the
final say on overlaps.
"""
from datetime import timedelta

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import clean_context

from ..models.pet import SPECIES
from ..models.reservation import WEEKDAY_ABBR, RECEPTION_HORIZON_DAYS, TZ, minutes_label

STEPS = [("what", "Co a kdy"), ("time", "Volný čas"), ("client", "Klient"), ("summary", "Shrnutí")]
# Manual time in quarter-hour steps 6:00–21:45 (key "HH:MM").
MANUAL_TIMES = [("%02d:%02d" % divmod(m, 60), minutes_label(m)) for m in range(6 * 60, 22 * 60, 15)]


def time_key(minute):
    """Minute -> manual time key (rounded down to a quarter hour); None when out of range."""
    m = (minute // 15) * 15
    key = "%02d:%02d" % divmod(m, 60)
    return key if key in dict(MANUAL_TIMES) else None


def today_in_prague():
    return pytz.utc.localize(fields.Datetime.now()).astimezone(TZ).date()


class ReservationWizard(models.TransientModel):
    _name = "elite.vet.reservation.wizard"
    _description = "Průvodce novou rezervací"

    step = fields.Selection(STEPS, string="Krok", default="what", required=True)

    # 1. What and when
    procedure_id = fields.Many2one("elite.vet.procedure", string="Úkon")
    allowed_doctor_ids = fields.Many2many("elite.vet.doctor", compute="_compute_allowed_doctors")
    duration = fields.Integer(string="Délka (min)", compute="_compute_duration", store=True, readonly=False,
                              help="Výchozí je délka úkonu. Prodlužte, když víte, že návštěva potrvá déle "
                                   "(např. dva psi).")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka",
                                domain="[('id', 'in', allowed_doctor_ids)]",
                                help="Volitelné. Nabízí se jen lékařky, které úkon dělají.")
    date = fields.Date(string="Datum", required=True, default=lambda self: today_in_prague())
    # Board click: who is on duty in that room at that time (and performs the procedure).
    # One doctor = selected automatically; several (overlapping shifts) = reception picks via button.
    serving_doctor_ids = fields.Many2many("elite.vet.doctor", compute="_compute_serving_doctors")
    has_multiple_serving = fields.Boolean(compute="_compute_serving_doctors")
    serving_doctor_id = fields.Many2one("elite.vet.doctor", string="Ve službě",
                                        domain="[('id', 'in', serving_doctor_ids)]",
                                        help="V tu dobu se v ordinaci překrývají služby více lékařek – vyberte, ke které.")

    # 2. Free time (also prefilled by a board click)
    minute = fields.Integer(string="Minuta od půlnoci")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace")
    slot_doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka termínu")
    slot_ids = fields.One2many("elite.vet.reservation.wizard.slot", "wizard_id", string="Volné časy")
    day_label = fields.Char(compute="_compute_day_label")
    warning = fields.Char(string="Upozornění", readonly=True,
                             help="Proč se předvyplněný čas z tabule nepoužil.")
    time_label = fields.Char(compute="_compute_time_label")
    # Manual slot: outside the offered times (closed, no shift, web-only block, weekend).
    manual = fields.Boolean(string="Zadat čas ručně",
                            help="Vložit rezervaci i mimo nabízené časy. Brání jen jiná rezervace "
                                 "a úplná blokace; ordinační doba, služba lékařky, blokace jen pro web, "
                                 "víkend ani svátek ne.")
    manual_room_id = fields.Many2one("elite.vet.room", string="Ordinace (ručně)")
    manual_time = fields.Selection(MANUAL_TIMES, string="Čas (ručně)")
    is_manual = fields.Boolean(help="Termín byl zadán ručně (pro shrnutí).")

    # 3. Client
    partner_mode = fields.Selection([("existing", "Existující klient"), ("new", "Nový klient")],
                                    string="Klient", default="existing", required=True)
    partner_id = fields.Many2one("res.partner", string="Vyhledat klienta", domain=[("type", "=", "contact")],
                                 help="Hledá podle jména, telefonu i e-mailu.")
    contact_name = fields.Char(string="Jméno a příjmení", compute="_compute_contact", store=True, readonly=False)
    contact_phone = fields.Char(string="Telefon", compute="_compute_contact", store=True, readonly=False)
    contact_email = fields.Char(string="E-mail", compute="_compute_contact", store=True, readonly=False)
    pet_id = fields.Many2one("elite.vet.pet", string="Mazlíček", domain="[('partner_id', '=', partner_id)]")
    pet_name = fields.Char(string="Nový mazlíček – jméno")
    pet_species = fields.Selection(SPECIES, string="Druh", default="dog")
    has_pet = fields.Boolean(compute="_compute_has_pet",
                                 help="Vybraný mazlíček patří vybranému existujícímu klientovi.")
    problem = fields.Text(string="Popis problému")
    note = fields.Text(string="Interní poznámka")
    send_email = fields.Boolean(string="Poslat klientovi potvrzení e-mailem",
                                compute="_compute_send_email", store=True, readonly=False)
    # The checkbox is pre-ticked only the first time an e-mail is filled in; afterwards the reception's choice applies.
    send_email_offered = fields.Boolean(compute="_compute_send_email", store=True, readonly=False)

    # 4. Summary
    summary = fields.Html(compute="_compute_summary", sanitize=False)

    # ---------- compute ----------
    @api.depends("procedure_id")
    def _compute_allowed_doctors(self):
        for w in self:
            w.allowed_doctor_ids = w.procedure_id.doctors_for_booking() if w.procedure_id else False

    @api.depends("procedure_id")
    def _compute_duration(self):
        # Changes only with the procedure; an extended duration survives doctor or date changes.
        for w in self:
            if w.procedure_id:
                w.duration = w.procedure_id.duration
            elif not w.duration:
                w.duration = 0

    @api.constrains("duration", "procedure_id")
    def _check_duration(self):
        for w in self:
            if w.procedure_id and (w.duration < 5 or w.duration % 5 or w.duration > 480):
                raise ValidationError(_("Délka musí být násobek 5 minut, nejméně 5 a nejvýše 480."))

    def _effective_duration(self):
        self.ensure_one()
        return self.duration or self.procedure_id.duration

    def action_extend_duration(self):
        self.ensure_one()
        self.duration = self._effective_duration() + int(self.env.context.get("extend_minutes", 15))
        return self._reopen()

    @api.depends("date")
    def _compute_day_label(self):
        for w in self:
            d = w.date
            w.day_label = "%s %d. %d. %d" % (WEEKDAY_ABBR[d.weekday()], d.day, d.month, d.year) if d else ""

    @api.depends("minute")
    def _compute_time_label(self):
        for w in self:
            w.time_label = minutes_label(w.minute)

    @api.depends("partner_id")
    def _compute_contact(self):
        # Without a selected client the contact is left alone: toggling Existing / New client
        # does not erase what reception typed for a new client (the selected client's
        # contact is cleared by _onchange_partner_mode).
        for w in self:
            if w.partner_id:
                w.contact_name = w.partner_id.name
                w.contact_phone = w.partner_id.phone or w.partner_id.mobile
                w.contact_email = w.partner_id.email

    @api.depends("contact_email")
    def _compute_send_email(self):
        for w in self:
            if not w.contact_email:
                w.send_email = False
            elif not w.send_email_offered:
                w.send_email = True
            w.send_email_offered = w.send_email_offered or bool(w.contact_email)

    @api.depends("partner_mode", "partner_id", "pet_id")
    def _compute_has_pet(self):
        for w in self:
            w.has_pet = bool(w._selected_pet())

    def _selected_partner(self):
        """Existing client the reservation will be saved for (empty recordset otherwise)."""
        self.ensure_one()
        if self.partner_mode == "existing" and self.partner_id:
            return self.partner_id
        return self.env["res.partner"]

    def _selected_pet(self):
        """Selected pet, only if it belongs to the selected existing client."""
        self.ensure_one()
        partner = self._selected_partner()
        if partner and self.pet_id and self.pet_id.partner_id == partner:
            return self.pet_id
        return self.env["elite.vet.pet"]

    @api.depends("procedure_id", "date", "minute", "room_id", "slot_doctor_id", "doctor_id", "contact_name",
                 "contact_phone", "contact_email", "partner_mode", "partner_id", "pet_id", "pet_name",
                 "pet_species", "send_email", "is_manual", "duration")
    def _compute_summary(self):
        species = dict(SPECIES)
        for w in self:
            # Same rule as action_save: only a pet of the selected client.
            selected_pet = w._selected_pet()
            pet = selected_pet.name or (w.pet_name or "").strip()
            if pet and not selected_pet and w.pet_species:
                pet = "%s (%s, nový)" % (pet, species.get(w.pet_species))
            client = w.contact_name or ""
            if not w._selected_partner():
                client += " (nový klient)"
            rows = [
                ("Úkon", w.procedure_id.name or ""),
                ("Termín", "%s %s–%s (%d min)%s" % (w.day_label, minutes_label(w.minute), minutes_label(w.minute + w._effective_duration()),
                                                    w._effective_duration(), " (zadáno ručně)" if w.is_manual else "")
                 if w.room_id else ""),
                ("Ordinace", w.room_id.name or ""),
                ("Lékařka", (w.slot_doctor_id or w.doctor_id).name or "—"),
                ("Klient", client),
                ("Kontakt", " · ".join(x for x in (w.contact_phone, w.contact_email) if x)),
                ("Mazlíček", pet or "—"),
                ("E-mail klientovi", "ano" if w.send_email and w.contact_email else "ne"),
            ]
            w.summary = Markup("<table class='table table-sm mb-0'>%s</table>") % Markup("").join(
                Markup("<tr><th class='w-25'>%s</th><td>%s</td></tr>") % (escape(k), escape(v)) for k, v in rows)

    @api.depends("room_id", "date", "minute", "procedure_id")
    def _compute_serving_doctors(self):
        for w in self:
            serving = w._serving_doctors()
            w.serving_doctor_ids = serving
            w.has_multiple_serving = len(serving) > 1

    def _serving_doctors(self):
        """Doctors on duty in the prefilled room at the prefilled time, ordered by
        shift start. If a procedure is selected, only those who perform it here."""
        Doctor = self.env["elite.vet.doctor"]
        if not (self.room_id and self.date):
            return Doctor
        assignments = self.env["elite.vet.doctor.assignment"].search(
            [("date", "=", self.date), ("room_id", "=", self.room_id.id),
             ("doctor_id.accepts_bookings", "=", True)], order="hour_from, id")
        out = Doctor
        for a in assignments:
            if a.hour_from * 60 <= self.minute < a.hour_to * 60 \
                    and (not self.procedure_id or a.serves(self.procedure_id)):
                out |= a.doctor_id
        return out

    @api.onchange("procedure_id", "room_id", "date", "minute")
    def _onchange_procedure(self):
        if self.doctor_id and self.procedure_id and self.doctor_id not in self.procedure_id.doctors_for_booking():
            self.doctor_id = False
        if not self.room_id:
            return
        serving = self._serving_doctors()
        if self.doctor_id in serving:
            self.serving_doctor_id = self.doctor_id
        elif len(serving) == 1:
            self.doctor_id = self.serving_doctor_id = serving
        elif len(serving) > 1:
            # Overlapping shifts: don't pick silently, let reception choose.
            self.doctor_id = self.serving_doctor_id = False

    @api.onchange("serving_doctor_id")
    def _onchange_serving_doctor(self):
        if self.serving_doctor_id:
            self.doctor_id = self.serving_doctor_id

    @api.onchange("doctor_id")
    def _onchange_doctor(self):
        if self.room_id and self.serving_doctor_id != self.doctor_id:
            self.serving_doctor_id = self.doctor_id if self.doctor_id in self._serving_doctors() else False

    @api.onchange("partner_mode")
    def _onchange_partner_mode(self):
        """Switching to a new client drops the selected client, their pet and contact."""
        if self.partner_mode == "new" and self.partner_id:
            self.partner_id = False
            self.pet_id = False
            self.contact_name = self.contact_phone = self.contact_email = False
            self.send_email_offered = False

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.pet_id and self.pet_id.partner_id != self.partner_id:
            self.pet_id = False
        if self.partner_id and not self.pet_id and len(self.partner_id.pet_ids) == 1:
            self.pet_id = self.partner_id.pet_ids

    # ---------- helpers ----------
    def _reopen(self):
        """Action that keeps the wizard dialog open on the current step."""
        return {
            "type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
            "name": _("Nová rezervace"), "view_mode": "form", "views": [[False, "form"]],
            "target": "new", "context": clean_context(self.env.context),
        }

    def _free_slots(self, day):
        # Reception books into every room with opening hours (including the operating
        # room, which is not online); the website still books online rooms only.
        A = self.env["elite.vet.availability"]
        # scope="internal": web-only blocks, weekends and holidays do not stop reception.
        return A.slots(self.procedure_id, day, doctor=self.doctor_id or None,
                       min_hours=0, max_days=RECEPTION_HORIZON_DAYS,
                       rooms=self.procedure_id.rooms_for_reception(), scope="internal",
                       duration=self._effective_duration())

    def _load_slots(self):
        """Fill the free-time lines for self.date: one line = time × room."""
        self.ensure_one()
        A = self.env["elite.vet.availability"]
        lines = [(5, 0, 0)]
        for slot in self._free_slots(self.date):
            for room_id, doc_id in A.room_doctors(self.procedure_id, self.date, slot, self.doctor_id or None,
                                          duration=self._effective_duration()):
                lines.append((0, 0, {"minute": slot["minute"], "room_id": room_id, "doctor_id": doc_id}))
        self.with_context(clean_context(self.env.context)).slot_ids = lines

    def _free_room_doctor(self):
        """(room_id, doctor_id) for the prefilled time and room if free; None otherwise."""
        A = self.env["elite.vet.availability"]
        slot = next((s for s in self._free_slots(self.date) if s["minute"] == self.minute), None)
        if not slot:
            return None
        return next((p for p in A.room_doctors(self.procedure_id, self.date, slot, self.doctor_id or None,
                                    duration=self._effective_duration())
                     if p[0] == self.room_id.id), None)

    def _collision(self, room, minute):
        """Reservation or full block that would overlap the manual slot (empty otherwise).
        Same rule as _check_overlap on save, which has the final say."""
        A = self.env["elite.vet.availability"]
        Res = self.env["elite.vet.reservation"]
        start = A.local_to_utc(self.date, minute)
        stop = start + timedelta(minutes=self._effective_duration())
        return Res.search(Res._busy_domain([room.id], start, stop, scope="internal"), limit=1)

    # ---------- steps ----------
    def action_step_time(self):
        """Step 1 → 2. A prefilled free time and room skip step 2.

        A board click outside the offered times (closed, no shift, web-only
        block, weekend) prefills the manual time with a warning; an occupied
        time does not.
        """
        self.ensure_one()
        if not self.procedure_id:
            raise UserError(_("Vyberte úkon."))
        warning = False
        manual_vals = {"manual": False}
        if self.room_id:
            room_doctor = self._free_room_doctor()
            if room_doctor:
                self.write({"slot_doctor_id": room_doctor[1] or self.doctor_id.id, "step": "client", "warning": False,
                            "is_manual": False, "manual": False})
                return self._reopen()
            key = time_key(self.minute)
            clash = self._collision(self.room_id, self.minute)
            if clash or not key:
                warning = _("%(time)s v %(room)s není pro tento úkon volný – vyberte jiný čas.",
                               time=minutes_label(self.minute), room=self.room_id.name)
            else:
                manual_vals = {"manual": True, "manual_room_id": self.room_id.id, "manual_time": key}
                warning = _("Mimo běžnou ordinační dobu – vkládáte ručně (%(time)s, %(room)s). "
                               "Zkontrolujte čas a pokračujte tlačítkem „Použít ruční čas“.",
                               time=minutes_label(self.minute), room=self.room_id.name)
        self.write(dict(manual_vals, room_id=False, slot_doctor_id=False, step="time", warning=warning,
                        is_manual=False))
        self._load_slots()
        return self._reopen()

    def action_use_manual_time(self):
        """Step 2 → 3 with a manually entered time and room.

        Opening hours, doctor shifts, web-only blocks, weekends and holidays do
        not block it; only another reservation or a full block does. The chosen
        doctor need not be on duty at that time.
        """
        self.ensure_one()
        if not self.procedure_id:
            raise UserError(_("Vyberte úkon."))
        if not (self.manual_room_id and self.manual_time):
            raise UserError(_("Vyberte ordinaci a čas."))
        hh, mm = (int(x) for x in self.manual_time.split(":"))
        minute = hh * 60 + mm
        clash = self._collision(self.manual_room_id, minute)
        if clash:
            raise UserError(_("%(time)s v %(room)s je obsazený: %(conflict)s.",
                              time=minutes_label(minute), room=self.manual_room_id.name, conflict=clash.name))
        doc = self.doctor_id
        if not doc:
            serving_ids = self.env["elite.vet.availability"].serving_doctors(
                self.procedure_id, self.date, self.manual_room_id.id, minute, duration=self._effective_duration())
            doc = self.env["elite.vet.doctor"].browse(serving_ids[:1])
        self.write({"minute": minute, "room_id": self.manual_room_id.id, "slot_doctor_id": doc.id or False,
                    "step": "client", "warning": False, "is_manual": True})
        return self._reopen()

    def action_back_to_what(self):
        self.write({"step": "what", "room_id": False, "slot_doctor_id": False, "minute": 0, "warning": False,
                    "manual": False, "is_manual": False})
        return self._reopen()

    def action_back_to_time(self):
        self.write({"step": "time", "room_id": False, "slot_doctor_id": False, "warning": False, "is_manual": False})
        self._load_slots()
        return self._reopen()

    def _shift_day(self, delta):
        self.write({"date": self.date + timedelta(days=delta)})
        self._load_slots()
        return self._reopen()

    def action_previous_day(self):
        return self._shift_day(-1)

    def action_next_day(self):
        return self._shift_day(1)

    def action_next_free_day(self):
        self.ensure_one()
        day = self.date
        for _i in range(RECEPTION_HORIZON_DAYS):
            day += timedelta(days=1)
            if self._free_slots(day):
                self.date = day
                self._load_slots()
                return self._reopen()
        raise UserError(_("V dalších %s dnech není pro tento úkon volný termín.") % RECEPTION_HORIZON_DAYS)

    def action_step_summary(self):
        """Step 3 → 4: validate the client details."""
        self.ensure_one()
        if self.partner_mode == "existing" and not self.partner_id:
            raise UserError(_("Vyhledejte klienta, nebo zvolte „Nový klient“."))
        if self.partner_mode == "new":
            if not (self.contact_name or "").strip():
                raise UserError(_("Vyplňte jméno a příjmení klienta."))
            if not (self.contact_phone or self.contact_email):
                raise UserError(_("Vyplňte telefon nebo e-mail klienta."))
        self.step = "summary"
        return self._reopen()

    def action_back_to_client(self):
        self.step = "client"
        return self._reopen()

    # ---------- save ----------
    def action_save(self):
        self.ensure_one()
        if not (self.procedure_id and self.room_id):
            raise UserError(_("Chybí úkon nebo termín."))
        env = self.with_context(clean_context(self.env.context)).env
        partner = self._selected_partner()
        pet = self._selected_pet()
        if not partner:
            partner = env["res.partner"].find_or_create_client(
                self.contact_name, self.contact_email, self.contact_phone)
        if not pet and (self.pet_name or "").strip():
            pet = env["elite.vet.pet"].find_or_create(partner, self.pet_name, self.pet_species)
        start = env["elite.vet.availability"].local_to_utc(self.date, self.minute)
        Res = env["elite.vet.reservation"]
        if not self.send_email:
            Res = Res.with_context(ev_no_mail=True)
        rec = Res.create({
            "kind": "reservation", "state": "confirmed", "source": "internal",
            "procedure_id": self.procedure_id.id, "room_id": self.room_id.id,
            "doctor_id": (self.slot_doctor_id or self.doctor_id).id or False,
            "start": start, "stop": start + timedelta(minutes=self._effective_duration()),
            "partner_id": partner.id, "pet_id": pet.id or False,
            "contact_name": self.contact_name or partner.name,
            "contact_phone": self.contact_phone or False, "contact_email": self.contact_email or False,
            "pet_name": pet.name or False, "pet_species": pet.species or self.pet_species or False,
            "problem": self.problem or False, "note": self.note or False,
            "lang": partner.lang or "cs_CZ",
        })
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success", "message": _("Rezervace uložena: %s") % rec.name,
                       "next": {"type": "ir.actions.act_window_close"}},
        }


class ReservationWizardSlot(models.TransientModel):
    _name = "elite.vet.reservation.wizard.slot"
    _description = "Volný čas v průvodci rezervací"
    _order = "minute, room_id"

    wizard_id = fields.Many2one("elite.vet.reservation.wizard", required=True, ondelete="cascade")
    minute = fields.Integer(required=True)
    time_label = fields.Char(string="Čas", compute="_compute_time_label")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka")

    @api.depends("minute")
    def _compute_time_label(self):
        for line in self:
            line.time_label = minutes_label(line.minute)

    def action_select(self):
        self.ensure_one()
        w = self.wizard_id
        w.write({"minute": self.minute, "room_id": self.room_id.id,
                 "slot_doctor_id": self.doctor_id.id or w.doctor_id.id, "step": "client", "is_manual": False})
        return w._reopen()
