"""WinVet -> Odoo bridge.

Reads the WinVet veterinary database (Firebird) strictly read-only and pushes the data to the
Odoo module ``elite_vet_winvet`` as described in ``CONTRACT.md``.
"""

__version__ = "2.0.0"

#: Push order required by the contract v2 (dependencies first).
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
)
