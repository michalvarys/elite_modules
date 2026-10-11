"""Průvodce „Nová rezervace“ pro recepci.

Čtyři kroky v jednom dialogu (pole `step`); tlačítka vrací akci téhož průvodce,
aby dialog zůstal otevřený. Volné časy počítá stejný engine jako web
(elite.vet.availability.slots), jen bez minimálního předstihu - recepce smí
objednat i na dnešek. Poslední slovo o překryvu má _check_overlap při uložení.
"""
from datetime import timedelta

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context

from ..models.pet import SPECIES
from ..models.reservation import DNY_KRATCE, HORIZONT_RECEPCE, TZ, cas_label

KROKY = [("co", "Co a kdy"), ("cas", "Volný čas"), ("klient", "Klient"), ("souhrn", "Shrnutí")]
# Ruční čas po čtvrthodinách 6:00–21:45 (klíč „HH:MM“).
RUCNI_CASY = [("%02d:%02d" % divmod(m, 60), cas_label(m)) for m in range(6 * 60, 22 * 60, 15)]


def klic_casu(minute):
    """Minuta -> klíč ručního času (zaokrouhleno dolů na čtvrthodinu), mimo rozsah None."""
    m = (minute // 15) * 15
    klic = "%02d:%02d" % divmod(m, 60)
    return klic if klic in dict(RUCNI_CASY) else None


def dnes_v_praze():
    return pytz.utc.localize(fields.Datetime.now()).astimezone(TZ).date()


class ReservationWizard(models.TransientModel):
    _name = "elite.vet.reservation.wizard"
    _description = "Průvodce novou rezervací"

    step = fields.Selection(KROKY, string="Krok", default="co", required=True)

    # 1. Co a kdy
    procedure_id = fields.Many2one("elite.vet.procedure", string="Úkon")
    povolene_lekarky_ids = fields.Many2many("elite.vet.doctor", compute="_compute_povolene_lekarky")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka",
                                domain="[('id', 'in', povolene_lekarky_ids)]",
                                help="Volitelné. Nabízí se jen lékařky, které úkon dělají.")
    date = fields.Date(string="Datum", required=True, default=lambda self: dnes_v_praze())

    # 2. Volný čas (předvyplní i klik do tabule)
    minute = fields.Integer(string="Minuta od půlnoci")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace")
    slot_doctor_id = fields.Many2one("elite.vet.doctor", string="Lékařka termínu")
    slot_ids = fields.One2many("elite.vet.reservation.wizard.slot", "wizard_id", string="Volné časy")
    den_label = fields.Char(compute="_compute_den_label")
    upozorneni = fields.Char(string="Upozornění", readonly=True,
                             help="Proč se předvyplněný čas z tabule nepoužil.")
    cas_label = fields.Char(compute="_compute_cas_label")
    # Ruční termín: mimo nabízené časy (zavřeno, bez služby, blokace jen pro web, víkend).
    manual = fields.Boolean(string="Zadat čas ručně",
                            help="Vložit rezervaci i mimo nabízené časy. Brání jen jiná rezervace "
                                 "a úplná blokace; ordinační doba, služba lékařky, blokace jen pro web, "
                                 "víkend ani svátek ne.")
    manual_room_id = fields.Many2one("elite.vet.room", string="Ordinace (ručně)")
    manual_time = fields.Selection(RUCNI_CASY, string="Čas (ručně)")
    rucne = fields.Boolean(help="Termín byl zadán ručně (pro shrnutí).")

    # 3. Klient
    partner_mode = fields.Selection([("existing", "Existující klient"), ("new", "Nový klient")],
                                    string="Klient", default="existing", required=True)
    partner_id = fields.Many2one("res.partner", string="Vyhledat klienta", domain=[("type", "=", "contact")],
                                 help="Hledá podle jména, telefonu i e-mailu.")
    contact_name = fields.Char(string="Jméno a příjmení", compute="_compute_kontakt", store=True, readonly=False)
    contact_phone = fields.Char(string="Telefon", compute="_compute_kontakt", store=True, readonly=False)
    contact_email = fields.Char(string="E-mail", compute="_compute_kontakt", store=True, readonly=False)
    pet_id = fields.Many2one("elite.vet.pet", string="Mazlíček", domain="[('partner_id', '=', partner_id)]")
    pet_name = fields.Char(string="Nový mazlíček – jméno")
    pet_species = fields.Selection(SPECIES, string="Druh", default="dog")
    ma_mazlicka = fields.Boolean(compute="_compute_ma_mazlicka",
                                 help="Vybraný mazlíček patří vybranému existujícímu klientovi.")
    problem = fields.Text(string="Popis problému")
    note = fields.Text(string="Interní poznámka")
    send_email = fields.Boolean(string="Poslat klientovi potvrzení e-mailem",
                                compute="_compute_send_email", store=True, readonly=False)
    # Zaškrtnutí se nabídne jen poprvé, když se e-mail vyplní; pak platí volba recepce.
    send_email_nabidnuto = fields.Boolean(compute="_compute_send_email", store=True, readonly=False)

    # 4. Shrnutí
    souhrn = fields.Html(compute="_compute_souhrn", sanitize=False)

    # ---------- compute ----------
    @api.depends("procedure_id")
    def _compute_povolene_lekarky(self):
        for w in self:
            w.povolene_lekarky_ids = w.procedure_id.doctors_for_booking() if w.procedure_id else False

    @api.depends("date")
    def _compute_den_label(self):
        for w in self:
            d = w.date
            w.den_label = "%s %d. %d. %d" % (DNY_KRATCE[d.weekday()], d.day, d.month, d.year) if d else ""

    @api.depends("minute")
    def _compute_cas_label(self):
        for w in self:
            w.cas_label = cas_label(w.minute)

    @api.depends("partner_id")
    def _compute_kontakt(self):
        # Bez vybraného klienta se kontakt nemění: přepínání Existující / Nový klient
        # nesmaže, co recepce u nového klienta napsala (kontakt vybraného maže
        # _onchange_partner_mode).
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
            elif not w.send_email_nabidnuto:
                w.send_email = True
            w.send_email_nabidnuto = w.send_email_nabidnuto or bool(w.contact_email)

    @api.depends("partner_mode", "partner_id", "pet_id")
    def _compute_ma_mazlicka(self):
        for w in self:
            w.ma_mazlicka = bool(w._vybrany_mazlicek())

    def _vybrany_klient(self):
        """Existující klient, ke kterému se rezervace uloží (jinak prázdný záznam)."""
        self.ensure_one()
        if self.partner_mode == "existing" and self.partner_id:
            return self.partner_id
        return self.env["res.partner"]

    def _vybrany_mazlicek(self):
        """Vybraný mazlíček, jen pokud patří vybranému existujícímu klientovi."""
        self.ensure_one()
        partner = self._vybrany_klient()
        if partner and self.pet_id and self.pet_id.partner_id == partner:
            return self.pet_id
        return self.env["elite.vet.pet"]

    @api.depends("procedure_id", "date", "minute", "room_id", "slot_doctor_id", "doctor_id", "contact_name",
                 "contact_phone", "contact_email", "partner_mode", "partner_id", "pet_id", "pet_name",
                 "pet_species", "send_email", "rucne")
    def _compute_souhrn(self):
        species = dict(SPECIES)
        for w in self:
            # Stejné pravidlo jako action_ulozit: mazlíček jen vybraného klienta.
            vybrany = w._vybrany_mazlicek()
            pet = vybrany.name or (w.pet_name or "").strip()
            if pet and not vybrany and w.pet_species:
                pet = "%s (%s, nový)" % (pet, species.get(w.pet_species))
            klient = w.contact_name or ""
            if not w._vybrany_klient():
                klient += " (nový klient)"
            radky = [
                ("Úkon", w.procedure_id.name or ""),
                ("Termín", "%s %s%s" % (w.den_label, cas_label(w.minute), " (zadáno ručně)" if w.rucne else "")
                 if w.room_id else ""),
                ("Ordinace", w.room_id.name or ""),
                ("Lékařka", (w.slot_doctor_id or w.doctor_id).name or "—"),
                ("Klient", klient),
                ("Kontakt", " · ".join(x for x in (w.contact_phone, w.contact_email) if x)),
                ("Mazlíček", pet or "—"),
                ("E-mail klientovi", "ano" if w.send_email and w.contact_email else "ne"),
            ]
            w.souhrn = Markup("<table class='table table-sm mb-0'>%s</table>") % Markup("").join(
                Markup("<tr><th class='w-25'>%s</th><td>%s</td></tr>") % (escape(k), escape(v)) for k, v in radky)

    @api.onchange("procedure_id")
    def _onchange_procedure(self):
        if self.doctor_id and self.procedure_id and self.doctor_id not in self.procedure_id.doctors_for_booking():
            self.doctor_id = False

    @api.onchange("partner_mode")
    def _onchange_partner_mode(self):
        """Přepnutí na nového klienta zahodí vybraného klienta i jeho mazlíčka a kontakt."""
        if self.partner_mode == "new" and self.partner_id:
            self.partner_id = False
            self.pet_id = False
            self.contact_name = self.contact_phone = self.contact_email = False
            self.send_email_nabidnuto = False

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.pet_id and self.pet_id.partner_id != self.partner_id:
            self.pet_id = False
        if self.partner_id and not self.pet_id and len(self.partner_id.pet_ids) == 1:
            self.pet_id = self.partner_id.pet_ids

    # ---------- pomocné ----------
    def _znovu(self):
        """Akce, která nechá dialog průvodce otevřený na aktuálním kroku."""
        return {
            "type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
            "name": _("Nová rezervace"), "view_mode": "form", "views": [[False, "form"]],
            "target": "new", "context": clean_context(self.env.context),
        }

    def _volne(self, day):
        # Recepce objednává do všech ordinací s ordinační dobou (i do Sálu, který
        # není online); web dál jen do online ordinací.
        A = self.env["elite.vet.availability"]
        # scope="internal": blokace jen pro web, víkend ani svátek recepci nebrání.
        return A.slots(self.procedure_id, day, doctor=self.doctor_id or None,
                       min_hours=0, max_days=HORIZONT_RECEPCE,
                       rooms=self.procedure_id.rooms_for_reception(), scope="internal")

    def _nacist_sloty(self):
        """Naplní řádky volných časů pro self.date: jeden řádek = čas × ordinace."""
        self.ensure_one()
        A = self.env["elite.vet.availability"]
        lines = [(5, 0, 0)]
        for slot in self._volne(self.date):
            for room_id, doc_id in A.room_doctors(self.procedure_id, self.date, slot, self.doctor_id or None):
                lines.append((0, 0, {"minute": slot["minute"], "room_id": room_id, "doctor_id": doc_id}))
        self.with_context(clean_context(self.env.context)).slot_ids = lines

    def _volny_par(self):
        """(room_id, doctor_id) pro předvyplněný čas a ordinaci, je-li volno; jinak None."""
        A = self.env["elite.vet.availability"]
        slot = next((s for s in self._volne(self.date) if s["minute"] == self.minute), None)
        if not slot:
            return None
        return next((p for p in A.room_doctors(self.procedure_id, self.date, slot, self.doctor_id or None)
                     if p[0] == self.room_id.id), None)

    def _kolize(self, room, minute):
        """Rezervace nebo úplná blokace, která by ruční termín překryla (jinak prázdné).
        Stejné pravidlo jako _check_overlap při uložení; ten má poslední slovo."""
        A = self.env["elite.vet.availability"]
        Res = self.env["elite.vet.reservation"]
        start = A.local_to_utc(self.date, minute)
        stop = start + timedelta(minutes=self.procedure_id.duration)
        return Res.search(Res._busy_domain([room.id], start, stop, scope="internal"), limit=1)

    # ---------- kroky ----------
    def action_krok_cas(self):
        """Krok 1 → 2. Předvyplněný volný čas a ordinace krok 2 přeskočí.

        Klik z tabule mimo nabízené časy (zavřeno, bez služby, blokace jen pro
        web, víkend) předvyplní ruční čas a jen upozorní; obsazený čas ne.
        """
        self.ensure_one()
        if not self.procedure_id:
            raise UserError(_("Vyberte úkon."))
        upozorneni = False
        rucni = {"manual": False}
        if self.room_id:
            par = self._volny_par()
            if par:
                self.write({"slot_doctor_id": par[1] or self.doctor_id.id, "step": "klient", "upozorneni": False,
                            "rucne": False, "manual": False})
                return self._znovu()
            klic = klic_casu(self.minute)
            clash = self._kolize(self.room_id, self.minute)
            if clash or not klic:
                upozorneni = _("%(cas)s v %(ordinace)s není pro tento úkon volný – vyberte jiný čas.",
                               cas=cas_label(self.minute), ordinace=self.room_id.name)
            else:
                rucni = {"manual": True, "manual_room_id": self.room_id.id, "manual_time": klic}
                upozorneni = _("Mimo běžnou ordinační dobu – vkládáte ručně (%(cas)s, %(ordinace)s). "
                               "Zkontrolujte čas a pokračujte tlačítkem „Použít ruční čas“.",
                               cas=cas_label(self.minute), ordinace=self.room_id.name)
        self.write(dict(rucni, room_id=False, slot_doctor_id=False, step="cas", upozorneni=upozorneni,
                        rucne=False))
        self._nacist_sloty()
        return self._znovu()

    def action_rucni_cas(self):
        """Krok 2 → 3 s ručně zadaným časem a ordinací.

        Ordinační doba, služba lékařky, blokace jen pro web, víkend ani svátek
        nebrání; brání jen jiná rezervace nebo úplná blokace. Zvolená lékařka
        nemusí mít v tu dobu službu.
        """
        self.ensure_one()
        if not self.procedure_id:
            raise UserError(_("Vyberte úkon."))
        if not (self.manual_room_id and self.manual_time):
            raise UserError(_("Vyberte ordinaci a čas."))
        hh, mm = (int(x) for x in self.manual_time.split(":"))
        minute = hh * 60 + mm
        clash = self._kolize(self.manual_room_id, minute)
        if clash:
            raise UserError(_("%(cas)s v %(ordinace)s je obsazený: %(co)s.",
                              cas=cas_label(minute), ordinace=self.manual_room_id.name, co=clash.name))
        doc = self.doctor_id
        if not doc:
            sluzi = self.env["elite.vet.availability"].serving_doctors(
                self.procedure_id, self.date, self.manual_room_id.id, minute)
            doc = self.env["elite.vet.doctor"].browse(sluzi[:1])
        self.write({"minute": minute, "room_id": self.manual_room_id.id, "slot_doctor_id": doc.id or False,
                    "step": "klient", "upozorneni": False, "rucne": True})
        return self._znovu()

    def action_zpet_co(self):
        self.write({"step": "co", "room_id": False, "slot_doctor_id": False, "minute": 0, "upozorneni": False,
                    "manual": False, "rucne": False})
        return self._znovu()

    def action_zpet_cas(self):
        self.write({"step": "cas", "room_id": False, "slot_doctor_id": False, "upozorneni": False, "rucne": False})
        self._nacist_sloty()
        return self._znovu()

    def _posun_den(self, delta):
        self.write({"date": self.date + timedelta(days=delta)})
        self._nacist_sloty()
        return self._znovu()

    def action_den_predchozi(self):
        return self._posun_den(-1)

    def action_den_dalsi(self):
        return self._posun_den(1)

    def action_dalsi_volny_den(self):
        self.ensure_one()
        day = self.date
        for _i in range(HORIZONT_RECEPCE):
            day += timedelta(days=1)
            if self._volne(day):
                self.date = day
                self._nacist_sloty()
                return self._znovu()
        raise UserError(_("V dalších %s dnech není pro tento úkon volný termín.") % HORIZONT_RECEPCE)

    def action_krok_souhrn(self):
        """Krok 3 → 4: kontrola údajů klienta."""
        self.ensure_one()
        if self.partner_mode == "existing" and not self.partner_id:
            raise UserError(_("Vyhledejte klienta, nebo zvolte „Nový klient“."))
        if self.partner_mode == "new":
            if not (self.contact_name or "").strip():
                raise UserError(_("Vyplňte jméno a příjmení klienta."))
            if not (self.contact_phone or self.contact_email):
                raise UserError(_("Vyplňte telefon nebo e-mail klienta."))
        self.step = "souhrn"
        return self._znovu()

    def action_zpet_klient(self):
        self.step = "klient"
        return self._znovu()

    # ---------- uložení ----------
    def action_ulozit(self):
        self.ensure_one()
        if not (self.procedure_id and self.room_id):
            raise UserError(_("Chybí úkon nebo termín."))
        env = self.with_context(clean_context(self.env.context)).env
        partner = self._vybrany_klient()
        pet = self._vybrany_mazlicek()
        if not partner:
            partner = env["res.partner"].najit_nebo_zalozit_klienta(
                self.contact_name, self.contact_email, self.contact_phone)
        if not pet and (self.pet_name or "").strip():
            pet = env["elite.vet.pet"].najit_nebo_zalozit(partner, self.pet_name, self.pet_species)
        start = env["elite.vet.availability"].local_to_utc(self.date, self.minute)
        Res = env["elite.vet.reservation"]
        if not self.send_email:
            Res = Res.with_context(ev_bez_mailu=True)
        rec = Res.create({
            "kind": "reservation", "state": "confirmed", "source": "internal",
            "procedure_id": self.procedure_id.id, "room_id": self.room_id.id,
            "doctor_id": (self.slot_doctor_id or self.doctor_id).id or False,
            "start": start, "stop": start + timedelta(minutes=self.procedure_id.duration),
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
            line.time_label = cas_label(line.minute)

    def action_vybrat(self):
        self.ensure_one()
        w = self.wizard_id
        w.write({"minute": self.minute, "room_id": self.room_id.id,
                 "slot_doctor_id": self.doctor_id.id or w.doctor_id.id, "step": "klient", "rucne": False})
        return w._znovu()
