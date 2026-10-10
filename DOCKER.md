# Nasazení přes Docker

Celý repozitář se v kontejneru mountuje do `/mnt/modules`. Moduly jsou v něm
po projektech, `elite_vet/` jsou moduly Elite Vet. Nic se nikam nekopíruje.

---

## A) Nová instalace na čistém stroji

```bash
git clone https://github.com/goatrental/elite_modules.git
cd elite_modules
docker compose up -d
```

Odoo naběhne na `http://localhost:8069`. Instalace modulu:

```bash
docker compose exec odoo odoo -d NAZEV_DATABAZE -i elite_vet_calendar --stop-after-init
docker compose restart odoo
```

> Před ostrým provozem změňte `admin_passwd` v `config/odoo.conf` a hesla
> databáze v `docker-compose.yml`.

---

## B) Nasazení do už běžícího Odoo v Dockeru

### Krok 0 — smazat stávající ruční stránku

Pokud v databázi ještě je ručně vytvořená stránka `/rozpis-lekaru`, musí pryč,
jinak modul narazí na stejnou URL a instalace spadne.

Web → Stránky → `/rozpis-lekaru` → smazat.

Na téhle stránce nejsou žádné překlady, takže se smazáním nic neztratí.

### Krok 1 — naklonovat repozitář na server

Kamkoli, kde na něj kontejner dosáhne, například vedle `docker-compose.yml`:

```bash
git clone https://github.com/goatrental/elite_modules.git
```

### Krok 2 — namountovat a přidat do addons_path

Do `docker-compose.yml` běžícího Odoo přidat volume:

```yaml
volumes:
  - ./elite_modules:/mnt/modules:ro
```

A do `odoo.conf` cestu ke složce projektu:

```ini
addons_path = /mnt/modules/elite_vet,/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
```

> Do `addons_path` patří složka **projektu** (`/mnt/modules/elite_vet`), ne složka
> modulu. Odoo si moduly uvnitř najde samo.

Aktualizace později:

```bash
cd elite_modules
git pull
```

### Krok 3 — práva

Odoo v oficiálním image běží pod UID 101. Pokud se modul v seznamu aplikací
neobjeví, bývá to právy:

```bash
sudo chown -R 101:101 elite_modules
```

### Krok 4 — instalace

```bash
docker compose up -d
docker compose exec odoo odoo -d NAZEV_DATABAZE -i elite_vet_calendar --stop-after-init
docker compose restart odoo
```

Aktualizace po změně kódu — místo `-i` použít `-u`:

```bash
docker compose exec odoo odoo -d NAZEV_DATABAZE -u elite_vet_calendar --stop-after-init
docker compose restart odoo
```

Nebo přes rozhraní: zapnout vývojářský režim → Aplikace → **Aktualizovat
seznam aplikací** → hledat `Rozpis` → Instalovat.

### Krok 5 — kontrola

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://elite-vet.cz/rozpis-lekaru
```

Očekávaná odpověď `200`. Stránka je publikovaná rovnou modulem.

Mřížka bude po instalaci prázdná — naplní se v Odoo v aplikaci
**Rozpis služeb**.

---

## Když se modul neobjeví v seznamu

| příznak | příčina |
|---|---|
| není v Aplikacích ani po *Aktualizovat seznam aplikací* | v `addons_path` chybí `/mnt/modules/elite_vet`, nebo je tam uvedená složka modulu místo složky projektu |
| v logu `Skipped unreadable module` | práva, viz krok 3 |
| instalace spadne na duplicitní URL | nesmazaná ruční stránka `/rozpis-lekaru`, viz krok 0 |
| aplikace je vidět, ale stránka hlásí 404 | modul nainstalovaný, ale stránka není publikovaná — Web → Stránky |

Log kontejneru:

```bash
docker compose logs -f --tail=100 odoo
```
