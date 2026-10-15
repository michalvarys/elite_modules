"""WinVet -> Odoo bridge.

Reads the WinVet veterinary database (Firebird) strictly read-only and pushes the data to the
Odoo module ``elite_vet_winvet`` as described in ``CONTRACT.md``.
"""

__version__ = "1.0.0"

#: Push order required by the contract (dependencies first).
ENTITY_ORDER = (
    "users",
    "items",
    "owners",
    "contacts",
    "patients",
    "vaccinations",
    "visits",
    "sale_documents",
    "sale_lines",
    "payments",
)
