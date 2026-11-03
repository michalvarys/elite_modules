from . import models

# Rows of the clinic's paper roster, top to bottom: (name, kind, room name, roles shown first,
# [(slot name, shift type time_from of the existing type, from, to, days)]).
DEFAULT_ROWS = [
    ("Recepce", "room", None, "reception,nurse", [
        ("Ranní", 8.0, 8.0, 16.0, "weekdays"),
        ("Odpolední", 14.0, 12.0, 20.0, "weekdays"),
        ("Víkend", 10.0, 10.0, 18.0, "weekend"),
    ]),
    ("Ordinace 1", "room", "Ordinace 1", "doctor,nurse", [
        ("Ranní", 8.0, 8.0, 16.0, "weekdays"),
        ("Odpolední", 14.0, 12.0, 20.0, "weekdays"),
        ("Víkend", 10.0, 10.0, 18.0, "weekend"),
    ]),
    ("Ordinace 2", "room", "Ordinace 2", "doctor,nurse", [
        ("Ranní", 8.0, 8.0, 16.0, "weekdays"),
        ("Odpolední", 14.0, 12.0, 20.0, "weekdays"),
    ]),
    ("Sál", "room", "Sál", "doctor,nurse", [
        ("Ranní", 8.0, 8.0, 16.0, "weekdays"),
    ]),
    ("Stáž / výpomoc", "helpers", None, "helper,nurse", [
        ("Praktikanti / brigádníci", 8.0, 8.0, 16.0, "all"),
    ]),
]


def _post_init(env):
    """Default rows and slots (once, like the shift types of elite_vet_calendar: what the clinic
    deletes stays deleted) and staff roles from the doctor flag."""
    _seed_rows(env)
    Doctor = env["elite.vet.doctor"].with_context(active_test=False)
    Doctor.search([("accepts_bookings", "=", True)]).write({"staff_role": "doctor"})


def _seed_rows(env):
    Row = env["elite.vet.planning.row"].with_context(active_test=False)
    if Row.search_count([]):
        return
    Room = env["elite.vet.room"].with_context(active_test=False)
    Type = env["elite.vet.shift.type"].with_context(active_test=False)
    regular = Type.search([("is_note", "=", False)], order="sequence, id")
    for seq, (name, kind, room_name, roles, slots) in enumerate(DEFAULT_ROWS, start=1):
        room = Room.search([("name", "=", room_name)], limit=1) if room_name else Room
        slot_vals = []
        for slot_seq, (slot_name, type_from, h_from, h_to, days) in enumerate(slots, start=1):
            shift_type = regular.filtered(lambda t: t.time_from == type_from)[:1] or regular[:1]
            if not shift_type:
                continue
            slot_vals.append((0, 0, {"name": slot_name, "sequence": slot_seq * 10, "type_id": shift_type.id,
                                     "hour_from": h_from, "hour_to": h_to, "days": days}))
        Row.create({"name": name, "sequence": seq * 10, "kind": kind, "room_id": room.id,
                    "preferred_roles": roles, "slot_ids": slot_vals})
