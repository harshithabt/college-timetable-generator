"""Constraint validation for the college timetable generator."""

from collections.abc import Mapping


REQUIRED_FIELDS = {"day", "slot", "teacher", "class_id", "room"}


def _validate_slot(slot):
    """Ensure a slot is a positive integer, excluding booleans."""
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 1:
        raise ValueError("Slot must be a positive integer")


def _validate_entry(entry):
    """Validate the structure and values of one timetable entry."""
    if not isinstance(entry, Mapping):
        raise ValueError("Every timetable entry must be a dictionary.")

    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        missing_fields = ", ".join(sorted(missing))
        raise ValueError(
            f"Timetable entry is missing fields: {missing_fields}"
        )

    # Validate the slot separately so None, booleans, strings,
    # floats, zero, and negative values receive the correct error.
    _validate_slot(entry["slot"])

    # Validate the remaining required fields.
    for field in ("day", "teacher", "class_id", "room"):
        value = entry[field]

        if value is None:
            raise ValueError(f"Field '{field}' cannot be empty.")

        if isinstance(value, str) and not value.strip():
            raise ValueError(f"Field '{field}' cannot be empty.")

    if not isinstance(entry["day"], str):
        raise ValueError("Field 'day' must be a string.")

    for field in ("teacher", "class_id", "room"):
        if not isinstance(entry[field], str):
            raise ValueError(f"Field '{field}' must be a string.")


def has_conflict(candidate, timetable):
    """Return True if candidate conflicts with an existing timetable entry."""
    _validate_entry(candidate)

    if not isinstance(timetable, list):
        raise ValueError("Timetable must be a list.")

    for existing in timetable:
        _validate_entry(existing)

        same_slot = (
            candidate["day"] == existing["day"]
            and candidate["slot"] == existing["slot"]
        )

        if not same_slot:
            continue

        if candidate["teacher"] == existing["teacher"]:
            return True

        if candidate["class_id"] == existing["class_id"]:
            return True

        if candidate["room"] == existing["room"]:
            return True

    return False


def validate_timetable(timetable):
    """Return (is_valid, errors) for a timetable with no resource clashes."""
    if not isinstance(timetable, list):
        raise ValueError("Timetable must be a list.")

    errors = []

    # Validate every entry independently, including single-entry timetables.
    for index, current in enumerate(timetable):
        try:
            _validate_entry(current)
        except ValueError as exc:
            errors.append(f"Entry {index} is invalid: {exc}")

    # Check conflicts only between entries that are individually valid.
    for index, current in enumerate(timetable):
        try:
            _validate_entry(current)
        except ValueError:
            continue

        for previous_index in range(index):
            previous = timetable[previous_index]

            try:
                _validate_entry(previous)
            except ValueError:
                continue

            if has_conflict(current, [previous]):
                errors.append(
                    f"Entry {index} conflicts with entry {previous_index}."
                )

    return len(errors) == 0, errors