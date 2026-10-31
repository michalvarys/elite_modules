# Elite Arena – automatické e-maily

Série e-mailů, do kterých se hráč zařadí sám podle návštěv z ggLeapu. Cron běží každou hodinu.
Najdete je v Herna → Marketing → Automatické e-maily.

**Po instalaci jsou všechny série vypnuté.** Spouští je tlačítko *Spustit*.

## Jak série funguje

- **Kdo se zařadí:**
  - *Dlouho u nás nebyl*: poslední návštěva před X až Y dny.
  - *Po první návštěvě*: první návštěva před X až Y dny.
  - Lze omezit počtem návštěv.
  - Jen kontakty s e-mailem, herním účtem a bez odhlášení z e-mailů (blacklist).
- **Jen nově splňující** (výchozí):
  - Zařadí se jen ti, kdo podmínku splní po spuštění, takže e-maily chodí postupně.
  - Zapnuté *Zařadit i ty, kdo podmínku splňují už teď* jednorázově zařadí i všechny současné.
  - Na datech z října 2026 by to u série „dlouho nebyli“ bylo asi 540 lidí.
  - Tlačítko *Kdo splňuje podmínky* je ukáže.
- **Kroky:**
  - *Den* je počet dní po zařazení.
  - Každý krok má šablonu e-mailu a volitelně odměnu, která se pošle jako osobní odkaz k vyzvednutí.
  - *Jen když odměnu ještě nevyzvedl* se hodí pro připomínky. E-mail bez nové odměny připomene odkaz z dřívějšího kroku.
  - *Poslat zkušební* pošle krok vám a odkaz v něm nic nepřidá.
- **Konec série:**
  - *Ukončit, když hráč přijde*: po návratu hráče další e-maily nepřijdou a zařazení dostane stav *Vrátil se*.
  - Odhlášení odkazem v patičce: potvrzuje se tlačítkem, aby odhlášení nespustily kontroly odkazů v poště.
  - Kontakt se přidá na blacklist a všechny jeho série se zastaví.
- **Výsledek:** série ukazuje, kolik zařazených se vrátilo a kolik vyzvedlo odměnu. Návrat se počítá do 120 dní od zařazení.

## Globální pravidla

Nastavují se v `ir.config_parameter` s prefixem `elite_arena_mail_sequence.`:

| Parametr | Výchozí | Význam |
|---|---|---|
| `send_hour_from` / `send_hour_to` | 9 / 20 | e-maily jen přes den (Praha) |
| `mails_per_run` | 40 | nejvýš e-mailů za hodinu |
| `gap_days` | 3 | dva automatické e-maily jednomu člověku aspoň takhle daleko od sebe |
| `enroll_per_run` | 300 | nejvýš nově zařazených za běh a sérii |

## Výchozí série

| Série | Podmínka | Kroky |
|---|---|---|
| Hráči, kteří dlouho nebyli | poslední návštěva před 45–180 dny; končí návratem; znovu nejdřív po 180 dnech | den 0 dárek (hodina zdarma), den 10 připomínka, pokud nevyzvedl |
| Noví hráči | první návštěva před 7–30 dny; jednou | den 0 poděkování + dárek |

Všechny automatické e-maily (i dotazník spokojenosti) odcházejí z `Elite Arena <no-reply@elite-arena.cz>`
(pole *Od* v šabloně; když je prázdné, použije se parametr `elite_arena_mail_sequence.email_from`,
výchozí je právě tahle adresa). Na no-reply se nedá odpovědět, proto se odhlašuje odkazem v patičce.

Texty e-mailů jsou šablony („Automaticky: …“) a jdou upravit. Šablony mají k dispozici
`object.first_name`, `object.reward_name`, `object.claim_url`, `object.claim_until`,
`object.pass_days` a `object.unsubscribe_url`.
