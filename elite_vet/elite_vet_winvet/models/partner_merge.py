from odoo import api, models


class PartnerMergeWizard(models.TransientModel):
    """Merging owners (standard wizard) must keep the WinVet link consistent.

    res.partner.winvet_ref is unique, and the standard merge copies values of the source
    partners into the destination before deleting the sources, which would collide. The
    destination keeps its own WinVet id (or takes the first one of the sources); all other
    WinVet ids become aliases, so the sync links their pets, contacts and documents to the
    destination instead of re-creating the deleted duplicates.
    """

    _inherit = "base.partner.merge.automatic.wizard"

    @api.model
    def _update_values(self, src_partners, dst_partner):
        everyone = src_partners | dst_partner
        if not any(p.winvet_ref or p.winvet_alias_refs for p in everyone):
            return super()._update_values(src_partners, dst_partner)
        refs = [int(p.winvet_ref) for p in src_partners if p.winvet_ref and p.winvet_ref.isdigit()]
        aliases = set(refs)
        for partner in everyone:
            aliases.update(partner._winvet_alias_list())
        primary = dst_partner.winvet_ref or (str(refs[0]) if refs else False)
        if primary and primary.isdigit():
            aliases.discard(int(primary))
        src_partners.write({"winvet_ref": False, "winvet_alias_refs": False})
        src_partners.flush_recordset()
        super()._update_values(src_partners, dst_partner)
        dst_partner.write({
            "winvet_ref": primary,
            "winvet_alias_refs": ",%s," % ",".join(str(a) for a in sorted(aliases)) if aliases else False,
            "winvet_merge_pending": False,
        })
