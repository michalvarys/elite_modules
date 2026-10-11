from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.elite_vet_calendar.models.vet_shift_type import COLORS

WEEKDAYS = [
    ("0", "Pondělí"), ("1", "Úterý"), ("2", "Středa"), ("3", "Čtvrtek"),
    ("4", "Pátek"), ("5", "Sobota"), ("6", "Neděle"),
]
WEEKDAY_SHORT = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]

COLOR_SELECTION = [
    ("green", "Zelená"), ("orange", "Oranžová"), ("purple", "Fialová"),
    ("pink", "Růžová"), ("red", "Červená"), ("blue", "Modrá"),
    ("teal", "Tyrkysová"), ("grey", "Šedá"),
]


def format_hour(value):
    """8.25 -> '8:15'. Stejne jako u typu smen, aby cisla vypadala vsude stejne."""
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return "%d:%02d" % (hours, minutes)


def format_hours_summary(lines):
    """[(den, od, do), …] -> „Po–Pá 8:15–19:30 · Ne 10:15–17:45“.

    Po sobě jdoucí dny se stejnými hodinami se sloučí; přestávka = dva časy
    za sebou („Po 8:00–12:00, 13:00–18:00“). Bez řádků prázdný text.
    """
    per_day = {}
    for wd, h_from, h_to in sorted(lines):
        per_day.setdefault(wd, []).append("%s–%s" % (format_hour(h_from), format_hour(h_to)))
    groups = []   # [[první den, poslední den, text]]
    for wd in range(7):
        if wd not in per_day:
            continue
        text = ", ".join(per_day[wd])
        if groups and groups[-1][1] == wd - 1 and groups[-1][2] == text:
            groups[-1][1] = wd
        else:
            groups.append([wd, wd, text])
    out = []
    for first, last, text in groups:
        days = WEEKDAY_SHORT[first] if first == last else "%s–%s" % (WEEKDAY_SHORT[first], WEEKDAY_SHORT[last])
        out.append("%s %s" % (days, text))
    return " · ".join(out)


class VetRoom(models.Model):
    """Ordinace = sloupec v kalendari. Sal je taky ordinace, jen ne online."""

    _name = "elite.vet.room"
    _description = "Ordinace"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    color = fields.Selection(COLOR_SELECTION, string="Barva", required=True, default="teal")
    color_hex = fields.Char(compute="_compute_color_hex")
    online = fields.Boolean(
        string="Rezervovatelná online", default=True,
        help="Odškrtněte u sálu nebo místnosti, kam se klienti nemají objednávat sami.")
    note = fields.Char(string="Poznámka")
    hours_ids = fields.One2many("elite.vet.room.hours", "room_id", string="Ordinační doba")
    exception_ids = fields.One2many("elite.vet.room.exception", "room_id", string="Výjimky")
    hours_summary = fields.Char(compute="_compute_hours_summary", string="Souhrn ordinační doby")
    active = fields.Boolean(string="Aktivní", default=True)

    @api.depends("color")
    def _compute_color_hex(self):
        for rec in self:
            rec.color_hex = COLORS.get(rec.color, COLORS["grey"])

    @api.depends("hours_ids.weekday", "hours_ids.hour_from", "hours_ids.hour_to",
                 "hours_ids.date_from", "hours_ids.date_to")
    @api.depends_context("tz")
    def _compute_hours_summary(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.hours_summary = format_hours_summary(
                (int(h.weekday), h.hour_from, h.hour_to)
                for h in rec.hours_ids if h.plati_v_den(today))


class VetRoomHours(models.Model):
    """Jeden radek tydenni sablony: den v tydnu, od, do.

    Vic radku na stejny den = prestavka (8-12 a 13-18). Platnost od/do slouzi
    na letni a zimni rezim bez mazani radku.
    """

    _name = "elite.vet.room.hours"
    _description = "Ordinační doba"
    _order = "room_id, weekday, hour_from"

    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, ondelete="cascade")
    weekday = fields.Selection(WEEKDAYS, string="Den", required=True, default="0")
    hour_from = fields.Float(string="Od", required=True, default=8.0)
    hour_to = fields.Float(string="Do", required=True, default=18.0)
    date_from = fields.Date(string="Platí od")
    date_to = fields.Date(string="Platí do")

    @api.depends("weekday", "hour_from", "hour_to")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s %s–%s" % (
                WEEKDAY_SHORT[int(rec.weekday or 0)], format_hour(rec.hour_from), format_hour(rec.hour_to))

    @api.constrains("hour_from", "hour_to", "weekday", "room_id", "date_from", "date_to")
    def _check_hours(self):
        for rec in self:
            if rec.hour_from >= rec.hour_to:
                raise ValidationError(_("Čas „Od“ musí být dřív než „Do“."))
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("Platnost „od“ je později než „do“."))
            others = self.search([
                ("id", "!=", rec.id), ("room_id", "=", rec.room_id.id), ("weekday", "=", rec.weekday),
            ])
            for other in others:
                if not rec._platnost_se_kryje(other):
                    continue
                if rec.hour_from < other.hour_to and other.hour_from < rec.hour_to:
                    raise ValidationError(_(
                        "Ordinační doba %s se překrývá s řádkem %s. Přestávku zadejte "
                        "jako dva řádky, které na sebe nenavazují přes stejný čas."
                    ) % (rec.display_name, other.display_name))

    def _platnost_se_kryje(self, other):
        """Dva radky si vadi jen kdyz plati ve stejnou dobu."""
        a_od, a_do = self.date_from or fields.Date.from_string("1900-01-01"), self.date_to or fields.Date.from_string("2999-12-31")
        b_od, b_do = other.date_from or fields.Date.from_string("1900-01-01"), other.date_to or fields.Date.from_string("2999-12-31")
        return a_od <= b_do and b_od <= a_do

    def plati_v_den(self, day):
        self.ensure_one()
        if self.date_from and day < self.date_from:
            return False
        if self.date_to and day > self.date_to:
            return False
        return True


class VetRoomException(models.Model):
    """Jeden den jinak: zavreno, nebo jine hodiny (i tam, kde sablona nic nema)."""

    _name = "elite.vet.room.exception"
    _description = "Výjimka ordinační doby"
    _order = "date desc"

    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, ondelete="cascade")
    date = fields.Date(string="Datum", required=True)
    closed = fields.Boolean(string="Zavřeno celý den")
    hour_from = fields.Float(string="Od")
    hour_to = fields.Float(string="Do")
    note = fields.Char(string="Poznámka", translate=True)

    _sql_constraints = [
        ("room_date_uniq", "unique(room_id, date)", "Na jeden den jde zadat jen jedna výjimka ordinace."),
    ]

    @api.depends("date", "closed", "hour_from", "hour_to", "note")
    def _compute_display_name(self):
        for rec in self:
            if rec.closed:
                rec.display_name = "%s – %s" % (rec.date or "", rec.note or _("zavřeno"))
            else:
                rec.display_name = "%s %s–%s" % (rec.date or "", format_hour(rec.hour_from), format_hour(rec.hour_to))

    @api.constrains("closed", "hour_from", "hour_to")
    def _check_times(self):
        for rec in self:
            if rec.closed:
                continue
            if not rec.hour_to or rec.hour_from >= rec.hour_to:
                raise ValidationError(_("U otevřeného dne vyplňte čas Od a Do (Od dřív než Do)."))
