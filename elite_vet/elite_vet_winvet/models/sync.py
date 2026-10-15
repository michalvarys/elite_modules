"""Receiving pushes from the WinVet bridge (see winvet_bridge/CONTRACT.md).

Every entity is upserted by its WinVet id (`winvet_ref`). References to other WinVet
rows are resolved by their WinVet ids; an unresolved reference keeps the raw id in an
`*_winvet_ref` integer field and `_fixups` links it at the end of every push call.
"""
import logging
from collections import defaultdict

from odoo import api, fields, models

from .contact import CONTACT_TYPE_CODES
from .item import CLASSIFICATIONS
from .payment import METHOD_CODES
from .winvet_tools import (
    ENTITIES, bad_date, map_species, normalize_phone, to_bool, to_date, to_float, to_int, to_str, to_utc_datetime,
)

_logger = logging.getLogger(__name__)

ENTITY_MODEL = {
    "users": "elite.vet.winvet.user",
    "items": "elite.vet.winvet.item",
    "owners": "res.partner",
    "contacts": "elite.vet.winvet.contact",
    "patients": "elite.vet.pet",
    "vaccinations": "elite.vet.vaccination",
    "visits": "elite.vet.visit",
    "sale_documents": "elite.vet.sale.document",
    "sale_lines": "elite.vet.sale.line",
    "payments": "elite.vet.payment",
}
# Master data are archived when deleted in WinVet, analytic rows are deleted.
MASTER = {"users", "items", "owners", "contacts", "patients"}
# res.partner.winvet_ref (defined by elite_vet_reservation) is a Char field.
CHAR_REF_MODELS = {"res.partner"}

OWNER_KINDS = {0: "company", 1: "person", 2: "group"}
CLASSIFICATION_KEYS = {key for key, _label in CLASSIFICATIONS}
CLASSIFICATION_CODES = {0: "group", 1: "product", 2: "set", 3: "kit", 4: "service", 5: "operation", 6: "alias"}
COUNTRY_ALIASES = {
    "ceska republika": "CZ", "cr": "CZ", "cesko": "CZ", "czech republic": "CZ",
    "slovensko": "SK", "slovenska republika": "SK", "sr": "SK",
    "nemecko": "DE", "spolkova republika nemecko": "DE", "rakousko": "AT", "polsko": "PL",
}

# Date/datetime keys per entity; invalid values (typo years) are stored empty and reported.
DATE_KEYS = {
    "owners": ("created", "modified"),
    "patients": ("birth_date", "death_date", "registered", "next_vaccination", "next_deworming",
                 "created", "modified"),
    "vaccinations": ("date", "next_date"),
    "visits": ("date",),
    "sale_documents": ("date",),
    "sale_lines": ("date",),
    "payments": ("date", "refunded_date"),
}

# (model, many2one field, raw ref field, target model) resolved after every push.
FIXUPS = [
    ("elite.vet.winvet.contact", "partner_id", "owner_winvet_ref", "res.partner"),
    ("elite.vet.pet", "partner_id", "winvet_owner_ref", "res.partner"),
    ("elite.vet.vaccination", "pet_id", "pet_winvet_ref", "elite.vet.pet"),
    ("elite.vet.vaccination", "item_id", "item_winvet_ref", "elite.vet.winvet.item"),
    ("elite.vet.visit", "pet_id", "pet_winvet_ref", "elite.vet.pet"),
    ("elite.vet.visit", "entered_by_id", "entered_by_winvet_ref", "elite.vet.winvet.user"),
    ("elite.vet.visit", "document_id", "document_winvet_ref", "elite.vet.sale.document"),
    ("elite.vet.sale.document", "parent_id", "parent_winvet_ref", "elite.vet.sale.document"),
    ("elite.vet.sale.document", "partner_id", "owner_winvet_ref", "res.partner"),
    ("elite.vet.sale.document", "entered_by_id", "entered_by_winvet_ref", "elite.vet.winvet.user"),
    ("elite.vet.sale.line", "document_id", "document_winvet_ref", "elite.vet.sale.document"),
    ("elite.vet.sale.line", "visit_id", "visit_winvet_ref", "elite.vet.visit"),
    ("elite.vet.sale.line", "item_id", "item_winvet_ref", "elite.vet.winvet.item"),
    ("elite.vet.sale.line", "entered_by_id", "entered_by_winvet_ref", "elite.vet.winvet.user"),
    ("elite.vet.payment", "document_id", "document_winvet_ref", "elite.vet.sale.document"),
    ("elite.vet.payment", "partner_id", "owner_winvet_ref", "res.partner"),
]


def _active(rec):
    return True if rec.get("active") is None else to_bool(rec.get("active"))


def _code(value, codes):
    """Accept both the documented string and the raw WinVet integer code."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip().lstrip("-").isdigit():
        return value.strip().lower()
    return codes.get(to_int(value), "other")


class WinvetSync(models.AbstractModel):
    _name = "elite.vet.winvet.sync"
    _description = "WinVet – příjem dat"

    # ------------------------------------------------------------------ entry points

    @api.model
    def _sync_env(self):
        return self.sudo().with_context(
            active_test=False, tracking_disable=True, mail_create_nolog=True, mail_notrack=True,
            mail_create_nosubscribe=True, lang="cs_CZ")

    @api.model
    def receive_status(self, payload):
        self = self._sync_env()
        self.env["elite.vet.winvet.status"].get_status().record_status(payload or {})
        return {"ok": True}

    @api.model
    def push(self, payload):
        self = self._sync_env()
        payload = payload or {}
        entity = payload.get("entity")
        if entity not in ENTITIES:
            return {"ok": False, "error": "unknown entity"}
        mode = payload.get("mode") or "incremental"
        if mode not in ("full", "incremental"):
            return {"ok": False, "error": "unknown mode"}
        batch = to_int(payload.get("batch")) or 1
        batches = to_int(payload.get("batches")) or 1
        run_id = to_str(payload.get("run_id"))
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
        errors = []

        records = {}
        for rec in payload.get("records") or []:
            ref = to_int(rec.get("id")) if isinstance(rec, dict) else False
            if not ref:
                stats["skipped"] += 1
                continue
            # PostgreSQL rejects NUL characters; an old bridge or odd data must not lose the record.
            records[ref] = {k: v.replace("\x00", "") if isinstance(v, str) else v for k, v in rec.items()}
        bad = ["%s.%s=%s" % (ref, key, rec[key]) for ref, rec in records.items()
               for key in DATE_KEYS.get(entity, ()) if bad_date(rec.get(key))]
        if bad:
            errors.append("neplatná data uložena jako prázdná: %s%s" % (", ".join(bad[:10]),
                                                                       " …" if len(bad) > 10 else ""))
        getattr(self, "_push_" + entity)(records, stats, errors, batch, batches)

        deleted = {to_int(r) for r in payload.get("deleted") or []} - {False, 0}
        if deleted:
            self._remove(entity, deleted, stats)

        if mode == "full":
            if not run_id:
                errors.append("plná synchronizace bez run_id – sesouhlasení přeskočeno")
            else:
                Run = self.env["elite.vet.winvet.run"]
                Run.store_batch(run_id, entity, batch, batches, list(records))
                if batch >= batches:
                    seen = Run.collect(run_id, entity, batches)
                    if seen is None:
                        errors.append("běh %s nemá všechny dávky – sesouhlasení přeskočeno" % run_id)
                    else:
                        self._reconcile(entity, seen, stats)
                    Run.cleanup(run_id, entity)

        self._fixups()
        self.env["elite.vet.winvet.status"].get_status().record_push(
            entity, mode, run_id, stats, "; ".join(errors[:5]) if errors else None)
        result = {"ok": True}
        result.update(stats)
        return result

    # ------------------------------------------------------------------ generic upsert

    @api.model
    def _diff(self, rec, vals):
        """Only the values that really differ from the stored ones."""
        out = {}
        for name, new in vals.items():
            field = rec._fields[name]
            old = rec[name]
            if field.type == "many2one":
                same = old.id == (new or False)
            elif field.type in ("float", "monetary"):
                same = abs((old or 0.0) - (new or 0.0)) < 1e-6
            elif field.type == "integer":
                same = (old or 0) == (new or 0)
            elif field.type == "boolean":
                same = bool(old) == bool(new)
            else:
                same = (old or False) == (new or False)
            if not same:
                out[name] = new
        return out

    @api.model
    def _ref_key(self, model_name, ref):
        return str(ref) if model_name in CHAR_REF_MODELS else ref

    @api.model
    def _ref_map(self, model_name, refs):
        """{winvet id: odoo id} for the given WinVet ids (archived rows included)."""
        refs = {r for r in refs if r}
        if not refs:
            return {}
        Model = self.env[model_name]
        recs = Model.search([("winvet_ref", "in", [self._ref_key(model_name, r) for r in refs])])
        return {int(r.winvet_ref): r.id for r in recs}

    @api.model
    def _upsert(self, model_name, vals_by_ref, stats, errors, create_extra=None):
        Model = self.env[model_name]
        existing = Model.search([("winvet_ref", "in", [self._ref_key(model_name, r) for r in vals_by_ref])])
        by_ref = {int(r.winvet_ref): r for r in existing}
        result = {}
        to_create = []
        for ref, vals in vals_by_ref.items():
            rec = by_ref.get(ref)
            if rec:
                diff = self._diff(rec, vals)
                if diff:
                    try:
                        with self.env.cr.savepoint():
                            rec.write(diff)
                        stats["updated"] += 1
                    except Exception as exc:  # noqa: BLE001 - one bad row must not stop the batch
                        self.env.invalidate_all()
                        stats["skipped"] += 1
                        errors.append("%s %s: %s" % (model_name, ref, exc))
                result[ref] = rec
            else:
                new_vals = dict(vals, winvet_ref=self._ref_key(model_name, ref))
                if create_extra:
                    new_vals.update(create_extra(vals))
                to_create.append(new_vals)
        if to_create:
            for rec in self._safe_create(Model, to_create, stats, errors):
                result[int(rec.winvet_ref)] = rec
        return result

    @api.model
    def _safe_create(self, Model, vals_list, stats, errors):
        try:
            with self.env.cr.savepoint():
                created = Model.create(vals_list)
            stats["created"] += len(created)
            return created
        except Exception:  # noqa: BLE001 - retry one by one to keep the good rows
            self.env.invalidate_all()
        created = Model.browse()
        for vals in vals_list:
            try:
                with self.env.cr.savepoint():
                    created |= Model.create(vals)
                stats["created"] += 1
            except Exception as exc:  # noqa: BLE001
                self.env.invalidate_all()
                stats["skipped"] += 1
                errors.append("%s %s: %s" % (Model._name, vals.get("winvet_ref"), exc))
        return created

    # ------------------------------------------------------------------ entities

    def _push_users(self, records, stats, errors, batch, batches):
        vals = {ref: {"name": to_str(r.get("name")) or "Uživatel %s" % ref,
                      "code": to_str(r.get("code")), "active": _active(r)}
                for ref, r in records.items()}
        users = self._upsert("elite.vet.winvet.user", vals, stats, errors)
        self.env["elite.vet.winvet.user"].concat(*users.values()).match_doctors()

    def _push_items(self, records, stats, errors, batch, batches):
        vals = {}
        for ref, r in records.items():
            cls = _code(r.get("classification"), CLASSIFICATION_CODES)
            vals[ref] = {
                "code": to_str(r.get("code")),
                "name": to_str(r.get("name")) or to_str(r.get("code")) or "Položka %s" % ref,
                "classification": cls if cls in CLASSIFICATION_KEYS else ("other" if cls else False),
                "stock_tracked": to_bool(r.get("stock_tracked")),
                "tracked_drug": to_bool(r.get("tracked_drug")),
                "unit": to_str(r.get("unit")),
                "barcode": to_str(r.get("barcode")),
                "active": _active(r),
            }
        self._upsert("elite.vet.winvet.item", vals, stats, errors)

    def _country_id(self, name, cache):
        name = to_str(name)
        if not name:
            return False
        if name not in cache:
            from .winvet_tools import strip_accents
            Country = self.env["res.country"]
            code = COUNTRY_ALIASES.get(strip_accents(name).lower())
            country = Country.search([("code", "=", code)], limit=1) if code else Country.browse()
            if not country and len(name) == 2:
                country = Country.search([("code", "=ilike", name)], limit=1)
            for lang in ("cs_CZ", "en_US"):
                if not country:
                    country = Country.with_context(lang=lang).search([("name", "=ilike", name)], limit=1)
            cache[name] = country.id or False
        return cache[name]

    def _push_owners(self, records, stats, errors, batch, batches):
        countries = {}
        vals = {}
        for ref, r in records.items():
            kind = _code(r.get("kind"), OWNER_KINDS)
            kind = kind if kind in ("company", "person", "group") else False
            first, last = to_str(r.get("first_name")), to_str(r.get("last_name"))
            name = to_str(r.get("name")) or " ".join(p for p in (last, first) if p) or "Bez jména"
            v = {
                "name": name,
                "is_company": kind == "company",
                "street": to_str(r.get("street")),
                "zip": to_str(r.get("zip")),
                "city": to_str(r.get("city")),
                "country_id": self._country_id(r.get("country"), countries),
                "company_registry": to_str(r.get("company_reg")),
                "winvet_vat": to_str(r.get("vat")),
                "winvet_kind": kind,
                "winvet_title": to_str(r.get("title")),
                "winvet_first_name": first,
                "winvet_last_name": last,
                "winvet_note": to_str(r.get("note")),
                "winvet_important_note": to_bool(r.get("important_note")),
                "winvet_created": to_date(r.get("created")),
                "winvet_modified": to_utc_datetime(r.get("modified")),
                "active": _active(r),
            }
            if kind == "person":
                v["is_vet_client"] = True
            vals[ref] = v
        self._upsert("res.partner", vals, stats, errors,
                     create_extra=lambda v: {"winvet_merge_pending": v.get("winvet_kind") == "person"})

    def _push_contacts(self, records, stats, errors, batch, batches):
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            owner = to_int(r.get("owner_id"))
            ctype = _code(r.get("type"), CONTACT_TYPE_CODES)
            vals[ref] = {
                "partner_id": partners.get(owner, False),
                "owner_winvet_ref": owner or False,
                "type": ctype if ctype in ("mobile", "phone", "fax", "email", "web") else "other",
                "value": to_str(r.get("value")),
                "label": to_str(r.get("label")),
                "active": True,
            }
        contacts = self._upsert("elite.vet.winvet.contact", vals, stats, errors)
        self._merge_pending_owners(self.env["res.partner"].browse(sorted(set(partners.values()))))
        # after linking, the contacts may belong to a different (existing) partner
        touched = self.env["elite.vet.winvet.contact"].concat(*contacts.values()).partner_id
        self._apply_contacts(touched)
        if batch >= batches:
            # Matching to existing web clients only happens in the run that created the owner.
            self.env["res.partner"].search([("winvet_merge_pending", "=", True)]).write(
                {"winvet_merge_pending": False})

    def _placeholder_owner(self):
        return self.env.ref("elite_vet_winvet.partner_unknown_owner")

    def _push_patients(self, records, stats, errors, batch, batches):
        placeholder = self._placeholder_owner()
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            owner = to_int(r.get("owner_id"))
            raw_species = to_str(r.get("species"))
            species, species_other = map_species(raw_species)
            vals[ref] = {
                "name": to_str(r.get("name")) or "Bez jména",
                "partner_id": partners.get(owner) or placeholder.id,
                "winvet_owner_ref": owner or False,
                "species": species,
                "species_other": species_other,
                "winvet_species": raw_species,
                "breed": to_str(r.get("breed")),
                "sex": to_str(r.get("sex")),
                "color": to_str(r.get("color")),
                "birth_date": to_date(r.get("birth_date")),
                "birth_year": to_int(r.get("birth_year")),
                "chip": to_str(r.get("chip")),
                "tattoo": to_str(r.get("tattoo")),
                "passport": to_str(r.get("passport")),
                "weight": to_float(r.get("weight")),
                "deceased": to_bool(r.get("deceased")),
                "death_date": to_date(r.get("death_date")),
                "active": _active(r),
                "registered_date": to_date(r.get("registered")),
                "next_vaccination": to_date(r.get("next_vaccination")),
                "next_deworming": to_date(r.get("next_deworming")),
                "important_note": to_str(r.get("important")),
                "winvet_note": to_str(r.get("note")),
                "winvet_created": to_date(r.get("created")),
                "winvet_modified": to_utc_datetime(r.get("modified")),
            }
        self._upsert("elite.vet.pet", vals, stats, errors)
        self._mark_clients(self.env["res.partner"].browse(set(partners.values())))

    def _mark_clients(self, partners):
        """Owners with patients are clients of the clinic (groups excepted)."""
        partners = partners - self._placeholder_owner()
        partners.filtered(lambda p: not p.is_vet_client and p.winvet_kind != "group"
                          and p.pet_ids).write({"is_vet_client": True})

    def _push_vaccinations(self, records, stats, errors, batch, batches):
        pets = self._ref_map("elite.vet.pet", {to_int(r.get("patient_id")) for r in records.values()})
        items = self._ref_map("elite.vet.winvet.item", {to_int(r.get("item_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            pet, item = to_int(r.get("patient_id")), to_int(r.get("item_id"))
            vals[ref] = {
                "pet_id": pets.get(pet, False), "pet_winvet_ref": pet or False,
                "date": to_date(r.get("date")), "next_date": to_date(r.get("next_date")),
                "item_id": items.get(item, False), "item_winvet_ref": item or False,
                "item_name": to_str(r.get("item_name")),
                "quantity": to_float(r.get("quantity")), "unit": to_str(r.get("unit")),
                "kind": to_int(r.get("kind")),
            }
        self._upsert("elite.vet.vaccination", vals, stats, errors)

    def _push_visits(self, records, stats, errors, batch, batches):
        pets = self._ref_map("elite.vet.pet", {to_int(r.get("patient_id")) for r in records.values()})
        users = self._ref_map("elite.vet.winvet.user", {to_int(r.get("entered_by")) for r in records.values()})
        docs = self._ref_map("elite.vet.sale.document", {to_int(r.get("document_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            pet, user, doc = to_int(r.get("patient_id")), to_int(r.get("entered_by")), to_int(r.get("document_id"))
            vals[ref] = {
                "pet_id": pets.get(pet, False), "pet_winvet_ref": pet or False,
                "date": to_date(r.get("date")), "time": to_str(r.get("time")),
                "case_name": to_str(r.get("case_name")),
                "diagnosis_code": to_str(r.get("diagnosis_code")),
                "diagnosis_name": to_str(r.get("diagnosis_name")),
                "entered_by_id": users.get(user, False), "entered_by_winvet_ref": user or False,
                "document_id": docs.get(doc, False), "document_winvet_ref": doc or False,
            }
        self._upsert("elite.vet.visit", vals, stats, errors)

    def _push_sale_documents(self, records, stats, errors, batch, batches):
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in records.values()})
        users = self._ref_map("elite.vet.winvet.user", {to_int(r.get("entered_by")) for r in records.values()})
        parents = self._ref_map("elite.vet.sale.document", {to_int(r.get("parent_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            owner, user, parent = to_int(r.get("owner_id")), to_int(r.get("entered_by")), to_int(r.get("parent_id"))
            vals[ref] = {
                "doc_type": to_str(r.get("type")), "number": to_str(r.get("number")),
                "parent_id": parents.get(parent, False), "parent_winvet_ref": parent or False,
                "partner_id": partners.get(owner, False), "owner_winvet_ref": owner or False,
                "date": to_date(r.get("date")),
                "total": to_float(r.get("total")), "paid": to_float(r.get("paid")),
                "from_deposit": to_float(r.get("from_deposit")),
                "state": to_str(r.get("state")),
                "entered_by_id": users.get(user, False), "entered_by_winvet_ref": user or False,
            }
        self._upsert("elite.vet.sale.document", vals, stats, errors)

    def _push_sale_lines(self, records, stats, errors, batch, batches):
        recs = records.values()
        docs = self._ref_map("elite.vet.sale.document", {to_int(r.get("document_id")) for r in recs})
        visits = self._ref_map("elite.vet.visit", {to_int(r.get("visit_id")) for r in recs})
        items = self._ref_map("elite.vet.winvet.item", {to_int(r.get("item_id")) for r in recs})
        users = self._ref_map("elite.vet.winvet.user", {to_int(r.get("entered_by")) for r in recs})
        vals = {}
        for ref, r in records.items():
            doc, visit = to_int(r.get("document_id")), to_int(r.get("visit_id"))
            item, user = to_int(r.get("item_id")), to_int(r.get("entered_by"))
            vals[ref] = {
                "document_id": docs.get(doc, False), "document_winvet_ref": doc or False,
                "visit_id": visits.get(visit, False), "visit_winvet_ref": visit or False,
                "item_id": items.get(item, False), "item_winvet_ref": item or False,
                "item_code": to_str(r.get("item_code")), "item_name": to_str(r.get("item_name")),
                "quantity": to_float(r.get("quantity")), "unit": to_str(r.get("unit")),
                "unit_price": to_float(r.get("unit_price")), "amount": to_float(r.get("amount")),
                "vat_rate": to_float(r.get("vat_rate")), "date": to_date(r.get("date")),
                "entered_by_id": users.get(user, False), "entered_by_winvet_ref": user or False,
            }
        self._upsert("elite.vet.sale.line", vals, stats, errors)

    def _push_payments(self, records, stats, errors, batch, batches):
        docs = self._ref_map("elite.vet.sale.document", {to_int(r.get("document_id")) for r in records.values()})
        partners = self._ref_map("res.partner", {to_int(r.get("owner_id")) for r in records.values()})
        vals = {}
        for ref, r in records.items():
            doc, owner = to_int(r.get("document_id")), to_int(r.get("owner_id"))
            code = (to_str(r.get("method")) or "").lower()
            vals[ref] = {
                "document_id": docs.get(doc, False), "document_winvet_ref": doc or False,
                "partner_id": partners.get(owner, False), "owner_winvet_ref": owner or False,
                "date": to_date(r.get("date")), "time": to_str(r.get("time")),
                "method": METHOD_CODES.get(code, "other") if code else False,
                "method_code": code or False,
                "amount": to_float(r.get("amount")), "from_deposit": to_float(r.get("from_deposit")),
                "state": to_str(r.get("state")), "refunded_date": to_date(r.get("refunded_date")),
            }
        self._upsert("elite.vet.payment", vals, stats, errors)

    # ------------------------------------------------------------------ owners <-> web clients

    def _merge_pending_owners(self, partners):
        """Rule: a person owner just created by the sync (winvet_merge_pending) whose
        WinVet e-mail or phone (last 9 digits) matches an existing active clinic client
        (is_vet_client) WITHOUT a WinVet id is linked to that client: the client gets the
        WinVet id and data, WinVet rows are moved to it and the freshly created duplicate
        is deleted. Never links to a partner that already has a (different) WinVet id."""
        Contact = self.env["elite.vet.winvet.contact"]
        for partner in partners.filtered("winvet_merge_pending"):
            contacts = Contact.search([("partner_id", "=", partner.id), ("active", "=", True)])
            emails = {c.value.strip().lower() for c in contacts if c.type == "email" and c.value}
            tails = {normalize_phone(c.value)[-9:] for c in contacts
                     if c.type in ("mobile", "phone") and len(normalize_phone(c.value)) >= 9}
            client = self._find_web_client(partner, emails, tails)
            if client:
                self._link_owner_to_client(partner, client)

    def _find_web_client(self, partner, emails, tails):
        Partner = self.env["res.partner"]
        base = [("is_vet_client", "=", True), ("active", "=", True), ("id", "!=", partner.id),
                "|", ("winvet_ref", "=", False), ("winvet_ref", "=", "")]
        client = Partner.browse()
        if emails:
            client = Partner.search(base + [("email_normalized", "in", list(emails))], order="id", limit=1)
        if not client and tails:
            Partner.flush_model(["phone", "mobile", "active", "is_vet_client", "winvet_ref"])
            self.env.cr.execute(
                "SELECT id FROM res_partner WHERE active AND is_vet_client AND id != %s"
                " AND coalesce(winvet_ref, '') = ''"
                " AND (right(regexp_replace(coalesce(phone, ''), '\\D', '', 'g'), 9) = ANY(%s)"
                "   OR right(regexp_replace(coalesce(mobile, ''), '\\D', '', 'g'), 9) = ANY(%s))"
                " ORDER BY id LIMIT 1",
                [partner.id, list(tails), list(tails)])
            client = Partner.browse([r[0] for r in self.env.cr.fetchall()])
        return client

    LINK_FIELDS = ["name", "is_company", "street", "zip", "city", "country_id", "company_registry",
                   "winvet_vat", "winvet_kind", "winvet_title", "winvet_first_name", "winvet_last_name",
                   "winvet_note", "winvet_important_note", "winvet_created", "winvet_modified"]

    def _link_owner_to_client(self, owner, client):
        if owner.user_ids or owner.reservation_ids:
            owner.winvet_merge_pending = False
            return
        vals = owner._convert_to_write({f: owner[f] for f in self.LINK_FIELDS})
        vals.update({"winvet_ref": owner.winvet_ref, "is_vet_client": True, "active": owner.active})
        owner.write({"winvet_ref": False, "winvet_merge_pending": False, "active": False})
        owner.flush_recordset()
        client.write(vals)
        for model_name in ("elite.vet.pet", "elite.vet.winvet.contact", "elite.vet.sale.document",
                           "elite.vet.payment"):
            self.env[model_name].search([("partner_id", "=", owner.id)]).write({"partner_id": client.id})
        try:
            with self.env.cr.savepoint():
                owner.unlink()
        except Exception:  # noqa: BLE001 - keep it archived when something still points to it
            self.env.invalidate_all()
        _logger.info("WinVet owner %s linked to existing client %s", vals["winvet_ref"], client.id)

    def _apply_contacts(self, partners):
        """WinVet is the master for e-mail, mobile and phone: the first WinVet contact
        of each type overwrites the partner's value. Missing types do not clear Odoo values."""
        partners -= self._placeholder_owner()
        if not partners:
            return
        contacts = self.env["elite.vet.winvet.contact"].search(
            [("partner_id", "in", partners.ids), ("active", "=", True), ("value", "!=", False)],
            order="winvet_ref")
        first = defaultdict(dict)
        for c in contacts:
            first[c.partner_id.id].setdefault(c.type, c.value)
        for partner in partners:
            values = first.get(partner.id, {})
            vals = {}
            for ctype, field in (("email", "email"), ("mobile", "mobile"), ("phone", "phone")):
                if values.get(ctype) and values[ctype] != partner[field]:
                    vals[field] = values[ctype]
            if vals:
                partner.write(vals)

    # ------------------------------------------------------------------ deletions, reconciliation, fixups

    def _remove(self, entity, refs, stats):
        model_name = ENTITY_MODEL[entity]
        recs = self.env[model_name].search([("winvet_ref", "in", [self._ref_key(model_name, r) for r in refs])])
        self._drop(entity, recs, stats)

    def _drop(self, entity, recs, stats):
        if entity in MASTER:
            recs = recs.filtered("active")
            recs.write({"active": False})
        else:
            recs.unlink()
        stats["deleted"] += len(recs)

    def _reconcile(self, entity, seen, stats):
        """Full run: rows of the entity whose WinVet id was not in any batch of the run."""
        Model = self.env[ENTITY_MODEL[entity]]
        Model.flush_model()
        where = "winvet_ref IS NOT NULL"
        if entity in MASTER:
            where += " AND active"
        self.env.cr.execute('SELECT id, winvet_ref FROM "%s" WHERE %s' % (Model._table, where))
        missing = []
        for rec_id, ref in self.env.cr.fetchall():
            try:
                ref = int(ref)
            except (TypeError, ValueError):
                continue  # a hand-typed non-numeric partner reference is left alone
            if ref and ref not in seen:
                missing.append(rec_id)
        if missing:
            self._drop(entity, Model.browse(missing), stats)

    def _fixups(self):
        """Link rows whose referenced WinVet row arrived later (cheap: only rows with a
        missing link and a stored raw id)."""
        self.env.flush_all()
        placeholder = self._placeholder_owner().id
        for model_name, field, ref_field, target_name in FIXUPS:
            Model, Target = self.env[model_name], self.env[target_name]
            join = "t.winvet_ref = s.%s::text" % ref_field if target_name in CHAR_REF_MODELS \
                else "t.winvet_ref = s.%s" % ref_field
            missing = "s.%s IS NULL" % field
            if model_name == "elite.vet.pet":
                missing = "(s.%s IS NULL OR s.%s = %d)" % (field, field, placeholder)
            self.env.cr.execute(
                'SELECT s.id, t.id FROM "%s" s JOIN "%s" t ON %s WHERE %s AND s.%s <> 0'
                % (Model._table, Target._table, join, missing, ref_field))
            by_target = defaultdict(list)
            for src_id, target_id in self.env.cr.fetchall():
                by_target[target_id].append(src_id)
            for target_id, src_ids in by_target.items():
                Model.browse(src_ids).write({field: target_id})
            if model_name == "elite.vet.pet" and by_target:
                # pets that just got their owner make the owner a clinic client
                self._mark_clients(Target.browse(list(by_target)))
        self.env.flush_all()
