"""Repetition rule of a block, as in WinVet's "Opakování události" (feedback 31. 10., B1).

Pure date arithmetic: the caller turns the dates into records (materialized copies)."""
import calendar
from datetime import date, timedelta

#: "Bez konce" creates the copies this far ahead (copies are records, they need an end)
NO_END_DAYS = 365
#: upper limit of the occurrences of one rule (a year of daily blocks fits)
MAX_OCCURRENCES = 400


def _add_months(day, months):
    """The same day `months` later, None when that month has no such day (31., 29. 2.)."""
    month0 = day.month - 1 + months
    year, month = day.year + month0 // 12, month0 % 12 + 1
    if day.day > calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, day.day)


def _candidates(start, rule, interval, weekdays):
    """Dates of the rule from `start` on, without end (ascending)."""
    k = 0
    while True:
        if rule == "daily":
            yield start + timedelta(days=k * interval)
        elif rule == "weekly":
            monday = start - timedelta(days=start.weekday()) + timedelta(weeks=k * interval)
            for wd in sorted(weekdays or (start.weekday(),)):
                day = monday + timedelta(days=wd)
                if day >= start:
                    yield day
        else:
            day = _add_months(start, k * interval * (12 if rule == "yearly" else 1))
            if day:
                yield day
        k += 1


def occurrence_dates(start, rule, interval, weekdays, end, count=0, until=None):
    """Dates of a repeated entry starting on `start`.

    rule: daily / weekly / monthly / yearly, every `interval` days / weeks / months / years;
    weekly on `weekdays` (0 = Monday; none = the day of `start`).
    end: never (NO_END_DAYS ahead) / count (that many dates) / until (inclusive)."""
    limit = until if end == "until" else start + timedelta(days=NO_END_DAYS)
    if end == "count":
        limit = date.max
    dates = []
    for day in _candidates(start, rule, interval, weekdays):
        # a far stop also for "count": a rule that skips days (31. of the month) still ends
        if day > limit or day > start + timedelta(days=366 * 20) or len(dates) >= MAX_OCCURRENCES:
            break
        dates.append(day)
        if end == "count" and len(dates) >= count:
            break
    return dates
