# Elite Arena – odměny k vyzvednutí

Odměna je herní pass z ggLeapu, například hodina zdarma. Hráč dostane osobní odkaz `/odmena/<kód>`.
Pass se mu do ggLeapu přidá **až ve chvíli, kdy na webu klikne na „Vyzvednout odměnu“**. Stránka je
běžná stránka webu, takže na ní běží retargeting (pixel) webu. Stránka má `noindex`.

- **Odměny** (Herna → Marketing → Odměny):
  - **Produkt:** pass vychází z produktu v ggLeapu. Prázdné pole = „1 HODINA FREE“ za 0 Kč.
  - **Herní čas** odměny.
  - **Platnost passu:** výchozí 14 dní od vyzvednutí.
  - **Platnost odkazu:** výchozí 30 dní.
  - **Text na stránce** pro vyzvednutí.
  - Odměna ukazuje, kolik odkazů bylo nabídnuto a kolik vyzvednuto.
- **Vyzvednutí odměn:** každý odkaz se stavem (*čeká*, *vyzvednuto*, *propadlo*), časem otevření a vyzvednutí a případnou chybou.
  - Filtr *Otevřel, ale nevyzvedl*.
  - Správce může odměnu přidat ručně tlačítkem *Přidat odměnu hráči teď*.
- **Bezpečnost:**
  - Dvojklik pass nepřidá dvakrát. Řádek se zamkne a ggLeap dostane stále stejný `X-Correlation-Id`.
  - Když ggLeap selže, odkaz zůstane platný a hráč to může zkusit znovu.
  - Zkušební odkazy nic nepřidají.
- **Herní účet:** hráč bez herního účtu u kontaktu odměnu nedostane. Stránka mu napíše, ať se ozve na baru.

Odkazy vytvářejí moduly `elite_arena_mail_sequence` a `elite_arena_satisfaction`.
