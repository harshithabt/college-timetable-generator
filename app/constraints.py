"""Constraint validation for the college timetable generator."""

from collections.abc import Mapping


REQUIRED_FIELDS = {"day", "slot", "teacher", "class_id", "room"}


def _validate_entry(entry):
    """Validate the structure of one timetable entry."""
    if not isinstance(entry, Mapping):
        raise ValueError("Every timetable entry must be a dictionary.")

    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        raise ValueError(
            f"Timetable entry is missing fields: {', '.join(sorted(missing))}"
        )

    for field in REQUIRED_FIELDS:
        value = entry[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"Field '{field}' cannot be empty.")


def has_conflict(candidate, timetable):
    """Return True if candidate conflicts with an existing timetable entry."""
    _validate_entry(candidate)

    if not isinstance(timetable, list):
        raise ValueError("Timetable must be a list.")

    for entry in timetable:
        _validate_entry(entry)

        same_slot = (
            candidate["day"] == entry["day"]
            and candidate["slot"] == entry["slot"]
        )

        if not same_slot:
            continue

        # A teacher, student class, or room can be used only once per slot.
        if candidate["teacher"] == entry["teacher"]:
            return True

        if candidate["class_id"] == entry["class_id"]:
            return True

        if candidate["room"] == entry["room"]:
            return True

    return False


def validate_timetable(timetable):
    """Return (is_valid, errors) for a complete timetable."""
    if not isinstance(timetable, list):
        raise ValueError("Timetable must be a list.")

    errors = []

    for index, entry in enumerate(timetable):
        _validate_entry(entry)

        for previous_index in range(index):
            previous = timetable[previous_index]

            if has_conflict(entry, [previous]):
                errors.append(
                    f"Entry {index} conflicts with entry {previous_index}."
                )

    return len(errors) == 0, errors