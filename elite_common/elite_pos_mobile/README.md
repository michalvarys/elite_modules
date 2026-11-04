# Elite – pokladna na mobilu

Sdílený modul pro všechny pokladny. Jen styl, žádná data.

- Kategorie mají vlastní posuvník, takže neodsunou produkty mimo obrazovku. Produkční sestavení Odoo 18
  to samo neumí: chybí mu třída `category-list`.
- Na telefonu jsou kategorie ve dvou řádcích posouvaných prstem do strany, pod nimi jsou produkty.
- Po klepnutí na skupinu zůstane vidět jen ona a její podkategorie; dalším klepnutím na ni se vrátíte zpět.

Nasazení je stejné jako u `elite_pos_l10n_cs`: `/mnt/modules/elite_common` v `addons_path`, jednou
`-i elite_pos_mobile`, restart a obnovení stránky pokladny.
