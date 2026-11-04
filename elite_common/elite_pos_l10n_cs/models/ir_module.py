import os
from contextlib import suppress

from odoo import models
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationImporter

from .code_translations import LANG, MODULE, po_path


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _load_module_terms(self, modules, langs, overwrite=False, imported_module=False):
        """Labels and views of the POS modules. Runs after the original files, without overwriting:
        only terms still without a Czech translation are filled, so edits made in Odoo are kept. A POS
        module installed later gets its terms here too."""
        super()._load_module_terms(modules, langs, overwrite=overwrite, imported_module=imported_module)
        if LANG not in langs:
            return
        if MODULE in modules:
            folder = file_path("%s/i18n_pos" % MODULE)
            names = [name.removesuffix(".po") for name in sorted(os.listdir(folder)) if name.endswith(".po")]
        else:
            names = modules
        importer = TranslationImporter(self.env.cr, verbose=False)
        for name in names:
            with suppress(FileNotFoundError):
                importer.load_file(po_path(name), LANG)
        importer.save(overwrite=False)
