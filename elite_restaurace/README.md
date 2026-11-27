# Restaurace

IMI a Jack Grill Bar jsou v jedné budově v Karlových Varech (každá na svém patře se svým skladem),
Staroslovanská kuchyně je v Lokti.

| Modul | Restaurace | Firma v Odoo | Lístek |
|---|---|---|---|
| `elite_imi_pos` | IMI Asia Sushi, 1. patro | „IMI Restaurant“, pobočka firmy Elite (SL FORTIS s.r.o.) | `IMI-menu-web.pdf` z 16. 11. 2026: 247 položek |
| `elite_jack_pos` | Jack Grill Bar, přízemí | „Jackgrillbar s.r.o.“, samostatná firma | lístek z 5. 7. 2026 (= web): 143 položek |
| `elite_loket_pos` | Staroslovanská kuchyně, Loket | „Přírodní Pivní Lázně s.r.o.“, samostatná firma | `Menu_Staroslovanska_Kuchyne_Loket_2026_web.pdf`: 82 položek |

Každá restaurace má vlastní pokladnu, sklad, řadu účtenek a sál s 12 stoly. Kód je ve společném
modulu [`elite_common/elite_restaurant_pos`](../elite_common/elite_restaurant_pos/README.md).

## Nasazení

1. Do `addons_path` na serveru přidat `/mnt/modules/elite_restaurace` (v repu už je
   v `config/odoo.conf`, `config/odoo-image.conf` a v `Dockerfile`).
2. Záloha a vypnutí demo dat (produkce je má zapnutá, viz README `elite_arena_pos`):
   ```bash
   docker compose exec db psql -U odoo -d odoo -c "UPDATE ir_module_module SET demo = false WHERE demo;"
   ```
3. Instalace a restart:
   ```bash
   docker compose exec odoo odoo -d odoo -i elite_imi_pos,elite_jack_pos,elite_loket_pos --stop-after-init --no-http
   docker compose restart odoo
   ```
4. Uživatelům obsluhy přidat přístup k firmě restaurace (Nastavení → Uživatelé → Povolené firmy).

Firmy podle názvů v `data/setup.xml`: když už v Odoo jsou (např. pod jiným názvem), opravte název
v `setup.xml` před instalací, jinak modul založí novou. U Jackgrillbar s.r.o. a Přírodní Pivní Lázně s.r.o. doplňte v Odoo IČO,
DIČ a adresu.

## Úprava lístku

Upravit `zbozi.csv` / `skupiny.csv`, spustit `gen_data.py` (viz README základu), commitnout. Na
nainstalované databázi se nové položky nahrají při `-u`; ceny a názvy existujících položek se mění
v Odoo (zboží je `noupdate`). Sazby DPH se podle `zbozi.csv` srovnají při každé aktualizaci.

## Testy

```bash
docker exec odoo odoo --addons-path=... -d TESTOVACI_DB -i elite_imi_pos,elite_jack_pos,elite_loket_pos \
  --test-tags /elite_imi_pos,/elite_jack_pos,/elite_loket_pos --stop-after-init --http-port 8094
```
Testovací databáze musí mít firmu „Elite“ (kopie `trafika_pos_prodlike`).
