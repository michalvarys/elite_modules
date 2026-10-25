"""Czech public holidays - moved to elite_vet_calendar (models/holidays.py).

Re-exported here so `from .holidays import holiday_name` and
`odoo.addons.elite_vet_reservation.models.holidays` keep working.
"""
from odoo.addons.elite_vet_calendar.models.holidays import (  # noqa: F401
    FIXED_HOLIDAYS,
    czech_holidays,
    easter_sunday,
    holiday_name,
    holidays_between,
)
