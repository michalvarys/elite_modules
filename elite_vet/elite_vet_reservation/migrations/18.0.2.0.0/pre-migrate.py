"""18.0.2.0.0: Czech identifiers renamed to English.

Stored fields are renamed in place (column + ir.model.fields + its xmlid) so Odoo
does not drop the old column with its data. Records that are noupdate (mail
templates, cron) still call the old method names and are fixed here as well.
"""

FIELDS = [
    # (model, table, old, new)
    ("elite.vet.doctor", "elite_vet_doctor", "prijima_rezervace", "accepts_bookings"),
    ("elite.vet.doctor", "elite_vet_doctor", "barva", "calendar_color"),
    ("elite.vet.procedure", "elite_vet_procedure", "barva_vlastni", "custom_color"),
    ("elite.vet.reservation", "elite_vet_reservation", "spojena_id", "linked_reservation_id"),
    ("elite.vet.reservation", "elite_vet_reservation", "druha_ordinace", "is_second_room"),
]

# Renamed xmlids: the record keeps its id, the update then rewrites it in place
# (otherwise the old view with old field names would break validation of the new one).
XMLIDS = [
    ("view_vet_doctor_form_rezervace", "view_vet_doctor_form_reservation"),
    ("view_vet_doctor_list_rezervace", "view_vet_doctor_list_reservation"),
    ("view_setting_rezervace_form_booking", "view_setting_reservation_form_booking"),
    ("view_druha_ordinace_wizard_form", "view_second_room_wizard_form"),
    ("rezervace_widget", "booking_widget"),
    ("action_assignment_kopirovat_tyden", "action_assignment_copy_week"),
    ("access_druha_wizard_reception", "access_second_room_wizard_reception"),
]

CODE = [
    ("mail_template", "email_from", "_odesilatel()", "_mail_sender()"),
    ("ir_act_server", "code", "_cron_pripominky()", "_cron_send_reminders()"),
]


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    for model, table, old, new in FIELDS:
        if not _column_exists(cr, table, old) or _column_exists(cr, table, new):
            continue
        cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"' % (table, old, new))
        cr.execute("UPDATE ir_model_fields SET name = %s WHERE model = %s AND name = %s", (new, model, old))
        model_ref = model.replace(".", "_")
        cr.execute(
            "UPDATE ir_model_data SET name = %s WHERE module = 'elite_vet_reservation' "
            "AND model = 'ir.model.fields' AND name = %s",
            ("field_%s__%s" % (model_ref, new), "field_%s__%s" % (model_ref, old)))
    for old, new in XMLIDS:
        cr.execute("UPDATE ir_model_data SET name = %s WHERE module = 'elite_vet_reservation' AND name = %s",
                   (new, old))
        # Website views are matched by key; website-specific copies (created for the
        # website-specific page) must keep the same key as the generic view, otherwise
        # both get applied and the second xpath fails.
        cr.execute("UPDATE ir_ui_view SET key = %s WHERE key = %s",
                   ("elite_vet_reservation." + new, "elite_vet_reservation." + old))
    for table, column, old, new in CODE:
        cr.execute('UPDATE "%s" SET "%s" = replace("%s", %%s, %%s) WHERE "%s" LIKE %%s'
                   % (table, column, column, column), (old, new, "%" + old + "%"))
