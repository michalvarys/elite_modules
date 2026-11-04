from contextlib import suppress

from odoo.tools import translate
from odoo.tools.misc import file_path

MODULE = "elite_pos_l10n_cs"
LANG = "cs_CZ"


def po_path(module_name):
    """Czech translation of `module_name` shipped by this module; raises FileNotFoundError when none."""
    return file_path("%s/i18n_pos/%s.po" % (MODULE, module_name))


def _patch_code_translations():
    """Code terms (JS and Python) are read only from the i18n folder of their own module, and Python
    terms are looked up per module, so a translation of another module needs this hook. The terms of
    this module win over the ones of the original file."""
    CodeTranslations = translate.CodeTranslations
    original = CodeTranslations._get_code_translations
    if getattr(original, "_elite_pos_l10n_cs", False):
        return

    def _get_code_translations(module_name, lang, filter_func):
        translations = original(module_name, lang, filter_func)
        if lang == LANG:
            with suppress(FileNotFoundError):
                with open(po_path(module_name), "rb") as fileobj:
                    translations.update(CodeTranslations._read_code_translations_file(fileobj, filter_func))
        return translations

    _get_code_translations._elite_pos_l10n_cs = True
    CodeTranslations._get_code_translations = staticmethod(_get_code_translations)
    # Terms read before this module was imported.
    translate.code_translations.python_translations.clear()
    translate.code_translations.web_translations.clear()


_patch_code_translations()
