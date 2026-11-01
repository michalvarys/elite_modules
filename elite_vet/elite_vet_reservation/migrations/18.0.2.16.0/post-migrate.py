"""18.0.2.16.0 (request 1. 11.): the cancellation e-mail shows the clinic's message to the client
(cancel_message). The template is noupdate, so the paragraph is added here to every language of
its body, after the first paragraph ("… has been cancelled."); the rest of the text, also when
edited by hand, stays. Idempotent."""
import json
import logging

_logger = logging.getLogger(__name__)

PARAGRAPH = ('\n    <p t-if="object.cancel_message" style="white-space:pre-line;padding:10px 14px;'
             'background:#f1f5f9;border-radius:6px" t-out="object.cancel_message"/>')


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT t.id, t.body_html FROM mail_template t
          JOIN ir_model_data d ON d.res_id = t.id AND d.model = 'mail.template'
         WHERE d.module = 'elite_vet_reservation' AND d.name = 'mail_cancelled'
    """)
    row = cr.fetchone()
    if not row or not row[1]:
        return
    template_id, body = row
    changed = []
    for lang, html in body.items():
        if not html or "cancel_message" in html or "</p>" not in html:
            continue
        at = html.index("</p>") + len("</p>")
        body[lang] = html[:at] + PARAGRAPH + html[at:]
        changed.append(lang)
    if changed:
        cr.execute("UPDATE mail_template SET body_html = %s WHERE id = %s", (json.dumps(body), template_id))
    _logger.info("elite_vet_reservation 18.0.2.16.0: cancellation message added to %s", ", ".join(changed) or "nothing")
