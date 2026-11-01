"""WinVet -> Odoo bridge.

Reads the WinVet veterinary database (Firebird) strictly read-only and pushes the data to the
Odoo module ``elite_vet_winvet`` as described in ``CONTRACT.md``.
"""

__version__ = "6.0.0"

#: Push order required by the contract v6 (dependencies first; v5 appends the deposits, v6 the
#: stock movements).
ENTITY_ORDER = (
    "users",
    "items",
    "owners",
    "contacts",
    "patients",
    "vaccinations",
    "visits",
    "vitals",
    "sale_documents",
    "sale_lines",
    "payments",
    "bundles",
    "bundle_lines",
    "phrases",
    "stock_lots",
    "stock_totals",
    "calendar_resources",
    "calendar_activities",
    "calendar_events",
    "deposits",
    "deposit_uses",
    "stock_moves",
)

#: Contract v4: the WinVet calendar (window read, may run on its own faster schedule).
CALENDAR_ENTITIES = ("calendar_resources", "calendar_activities", "calendar_events")

#: Contract v5: client deposits (PARTNER_ZALOHA) and their use in documents (PARTNER_ZALOHA_CERPANI).
DEPOSIT_ENTITIES = ("deposits", "deposit_uses")
