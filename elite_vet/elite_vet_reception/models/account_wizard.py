"""Wizard "Vytvořit účty" (task 23): one internal account per team member of Rozpis služeb ›
Lékařky that has none yet, linked to her (elite.vet.doctor.user_id).

- One line per active team member without an account: login = e-mail of her card in Náš tým
  (empty without it – then it must be filled to tick the line), role Lékařka for doctors who
  accept bookings, else Sestra (Recepce / Sestra / Lékařka / Správce rezervací selectable).
- The accounts get the role group only; the role automation of res.users (home screen, till group
  only for Recepce) does the rest. Language cs_CZ, time zone Europe/Prague, no password.
- "Poslat pozvánku e-mailem" (off by default): the standard Odoo invitation (auth_signup
  "set password" mail) is queued in the mail queue, it is not sent right away.
- Vedení only (group_reservation_manager); the users are created under sudo after that check.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
ROLE_GROUPS = {
    "reception": "elite_vet_reservation.group_reservation_reception",
    "nurse": "elite_vet_clinic.group_clinic_nurse",
    "doctor": "elite_vet_clinic.group_clinic_doctor",
    "manager": MANAGER_GROUP,
}
ROLES = [("reception", "Recepce"), ("nurse", "Sestra"), ("doctor", "Lékařka"), ("manager", "Správce rezervací")]
LANG = "cs_CZ"
TZ = "Europe/Prague"
INVITATION_TEMPLATE = "auth_signup.set_password_email"


def check_manager(env):
    if not env.user.has_group(MANAGER_GROUP):
        raise AccessError(_("Účty členů týmu může vytvářet jen vedení."))


class AccountWizard(models.TransientModel):
    _name = "elite.vet.account.wizard"
    _description = "Vytvořit účty členů týmu"

    line_ids = fields.One2many("elite.vet.account.wizard.line", "wizard_id", string="Členové týmu bez účtu")
    send_invitation = fields.Boolean(
        string="Poslat pozvánku e-mailem",
        help="Každému novému účtu se zařadí do fronty e-mailů standardní pozvánka Odoo s odkazem na "
             "nastavení hesla. Bez zaškrtnutí se nic neposílá – heslo pak nastaví správce.")

    @api.model
    def default_get(self, fields_list):
        check_manager(self.env)
        res = super().default_get(fields_list)
        if "line_ids" in fields_list:
            doctors = self.env["elite.vet.doctor"].search([("user_id", "=", False)], order="name, id")
            res["line_ids"] = [(0, 0, self._line_defaults(d)) for d in doctors]
        return res

    @api.model
    def _line_defaults(self, doctor):
        login = (doctor.member_id.email or "").strip()
        return {
            "doctor_id": doctor.id, "login": login or False,
            "role": "doctor" if doctor.accepts_bookings else "nurse",
            "create_account": bool(login),
        }

    @api.model
    def action_open(self):
        """Button Vytvořit účty on the Lékařky list and the server action."""
        check_manager(self.env)
        return {
            "type": "ir.actions.act_window", "name": _("Vytvořit účty"),
            "res_model": self._name, "view_mode": "form", "target": "new",
            "views": [(self.env.ref("elite_vet_reception.view_account_wizard_form").id, "form")],
        }

    def _check_lines(self, lines):
        """Ticked lines: a login, unique among the lines and among all users (also archived)."""
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        seen = {}
        for line in lines:
            label = line.doctor_id.name
            login = (line.login or "").strip()
            if not login:
                raise UserError(_("Řádek „%s“: vyplňte přihlašovací jméno (e-mail), nebo zrušte Vytvořit.") % label)
            key = login.lower()
            if key in seen:
                raise UserError(_("Řádky „%(a)s“ a „%(b)s“ mají stejné přihlašovací jméno %(login)s. "
                                  "Každý účet musí mít jiné.", a=seen[key], b=label, login=login))
            seen[key] = label
            other = Users.search([("login", "=ilike", login)], limit=1)
            if other:
                raise UserError(_("Řádek „%(line)s“: přihlašovací jméno %(login)s už má účet „%(user)s“. "
                                  "Zadejte jiné, nebo účet propojte ručně ve sloupci Účet.",
                                  line=label, login=login, user=other.name))
            if self.send_invitation and "@" not in login:
                raise UserError(_("Řádek „%s“: pozvánka jde poslat jen na e-mail – přihlašovací jméno "
                                  "není e-mailová adresa.") % label)

    def _user_vals(self, line):
        login = line.login.strip()
        vals = {
            "name": line.doctor_id.name, "login": login, "tz": TZ,
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref(ROLE_GROUPS[line.role]).id])],
        }
        if "@" in login:
            vals["email"] = login
        if self.env["res.lang"]._lang_get(LANG):
            vals["lang"] = LANG
        return vals

    def action_create(self):
        self.ensure_one()
        check_manager(self.env)
        ticked = self.line_ids.filtered("create_account")
        self._check_lines(ticked)
        created = self.env["res.users"]
        skipped = {"unticked": len(self.line_ids - ticked), "linked": 0}
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        for line in ticked:
            doctor = line.doctor_id.sudo()
            if doctor.user_id:
                skipped["linked"] += 1   # linked meanwhile (another tab, by hand)
                continue
            user = Users.create(self._user_vals(line))
            doctor.user_id = user
            created |= user
        if self.send_invitation and created:
            created._elite_vet_queue_invitation()
        parts = []
        if skipped["unticked"]:
            parts.append(_("nezaškrtnuto %s", skipped["unticked"]))
        if skipped["linked"]:
            parts.append(_("mezitím už účet měli %s", skipped["linked"]))
        message = _("Vytvořeno účtů: %s.", len(created))
        if parts:
            message += " " + _("Přeskočeno: %(count)s (%(why)s).",
                               count=skipped["unticked"] + skipped["linked"], why=", ".join(parts))
        if created:
            message += " " + (_("Pozvánky jsou ve frontě e-mailů.") if self.send_invitation
                              else _("Hesla nastavte v Nastavení › Uživatelé (nic se neposlalo)."))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success" if created else "warning", "title": _("Vytvořit účty"),
                       "message": message, "sticky": True,
                       "next": {"type": "ir.actions.client", "tag": "soft_reload"}},
        }


class AccountWizardLine(models.TransientModel):
    _name = "elite.vet.account.wizard.line"
    _description = "Vytvořit účty – člen týmu"
    _order = "id"

    wizard_id = fields.Many2one("elite.vet.account.wizard", required=True, ondelete="cascade")
    doctor_id = fields.Many2one("elite.vet.doctor", string="Člen týmu", required=True, readonly=True,
                                ondelete="cascade")
    login = fields.Char(string="Přihlašovací jméno",
                        help="E-mail z karty v Náš tým. Bez něj ho vyplňte, jinak řádek nejde vytvořit.")
    role = fields.Selection(ROLES, string="Role", required=True, default="nurse")
    create_account = fields.Boolean(string="Vytvořit")


class ResUsersInvitation(models.Model):
    _inherit = "res.users"

    def _elite_vet_queue_invitation(self):
        """The standard invitation (auth_signup set-password mail with the signup link), queued in
        the mail queue (mail.mail, sent by the mail cron) instead of sent right away."""
        template = self.env.ref(INVITATION_TEMPLATE, raise_if_not_found=False)
        if not template:
            raise UserError(_("Šablona pozvánky (auth_signup) chybí."))
        template = template.sudo()   # renders the signup link (needs write on res.users)
        mails = self.env["mail.mail"]
        for user in self.sudo():
            user.partner_id.signup_prepare(signup_type="signup")
            mail_id = template.send_mail(user.id, force_send=False, raise_exception=True, email_values={
                "email_to": user.email, "email_cc": False, "auto_delete": True,
                "message_type": "user_notification", "recipient_ids": [], "partner_ids": [],
                "scheduled_date": False})
            mails |= mails.browse(mail_id)
        return mails
