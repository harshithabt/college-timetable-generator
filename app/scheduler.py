"""Constraint-aware college timetable generation using backtracking."""

from app.constraints import has_conflict, validate_timetable


def generate_timetable(
    subjects,
    rooms,
    days,
    slots_per_day,
    teacher_availability=None,
):
    """
    Generate a complete timetable without teacher, class, or room clashes.

    Each subject must contain:
        subject_id: Unique subject identifier.
        teacher: Teacher identifier.
        class_id: Student class identifier.
        periods_per_week: Number of required weekly periods.

    teacher_availability is optional. For a listed teacher, it specifies
    allowed (day, slot) pairs. Teachers omitted from the mapping are
    considered available at all configured times.

    Returns:
        A list of dictionaries with day, slot, subject_id, teacher,
        class_id, and room.

    Raises:
        ValueError: If inputs are invalid or no complete timetable exists.
        RuntimeError: If the generated timetable fails final validation.
    """
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("Provide at least one subject.")

    if not isinstance(rooms, list) or not rooms:
        raise ValueError("Provide at least one room.")

    if not isinstance(days, list) or not days:
        raise ValueError("Provide at least one day.")

    if (
        not isinstance(slots_per_day, int)
        or isinstance(slots_per_day, bool)
        or slots_per_day < 1
    ):
        raise ValueError("slots_per_day must be a positive integer.")

    for name, values in (("rooms", rooms), ("days", days)):
        if any(
            not isinstance(value, str) or not value.strip()
            for value in values
        ):
            raise ValueError(
                f"Every item in {name} must be a non-empty string."
            )

        if len(set(values)) != len(values):
            raise ValueError(
                f"{name.capitalize()} must not contain duplicates."
            )

    if teacher_availability is None:
        teacher_availability = {}
    elif not isinstance(teacher_availability, dict):
        raise ValueError(
            "teacher_availability must be a dictionary or None."
        )

    valid_slots = {
        (day, slot)
        for day in days
        for slot in range(1, slots_per_day + 1)
    }

    # Validate and normalize availability without modifying caller data.
    normalized_availability = {}

    for teacher, available_slots in teacher_availability.items():
        if not isinstance(teacher, str) or not teacher.strip():
            raise ValueError(
                "Teacher IDs in teacher_availability must be non-empty strings."
            )

        if not isinstance(
            available_slots, (list, tuple, set, frozenset)
        ):
            raise ValueError(
                f"Availability for teacher '{teacher}' must be a collection "
                "of (day, slot) pairs."
            )

        normalized_slots = set()

        for pair in available_slots:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(
                    f"Invalid availability entry for teacher '{teacher}': "
                    f"{pair!r}."
                )

            day, slot = pair

            # Validate each member before constructing or hashing a pair.
            if not isinstance(day, str) or not day.strip():
                raise ValueError(
                    f"Availability contains an invalid day: {day!r}."
                )

            if day not in days:
                raise ValueError(
                    f"Availability contains an invalid slot: {pair!r}."
                )

            if (
                not isinstance(slot, int)
                or isinstance(slot, bool)
                or slot < 1
                or slot > slots_per_day
            ):
                raise ValueError(
                    f"Availability contains an invalid slot: {pair!r}."
                )

            normalized_pair = (day, slot)

            if normalized_pair not in valid_slots:
                raise ValueError(
                    f"Availability contains an invalid slot: {pair!r}."
                )

            normalized_slots.add(normalized_pair)

        normalized_availability[teacher] = normalized_slots

    required_fields = {
        "subject_id",
        "teacher",
        "class_id",
        "periods_per_week",
    }

    tasks = []
    seen_subject_ids = set()

    for subject in subjects:
        if not isinstance(subject, dict):
            raise ValueError("Every subject must be a dictionary.")

        missing = required_fields - subject.keys()
        if missing:
            raise ValueError(
                f"Subject is missing fields: {', '.join(sorted(missing))}"
            )

        for field in ("subject_id", "teacher", "class_id"):
            value = subject[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Subject field '{field}' must be a non-empty string."
                )

        subject_id = subject["subject_id"]

        if subject_id in seen_subject_ids:
            raise ValueError(f"Duplicate subject ID: {subject_id}.")

        seen_subject_ids.add(subject_id)

        periods = subject["periods_per_week"]

        if (
            not isinstance(periods, int)
            or isinstance(periods, bool)
            or periods < 1
        ):
            raise ValueError(
                f"periods_per_week for '{subject_id}' "
                "must be a positive integer."
            )

        for period_number in range(1, periods + 1):
            tasks.append(
                {
                    "subject_id": subject_id,
                    "teacher": subject["teacher"],
                    "class_id": subject["class_id"],
                    "period_number": period_number,
                }
            )

    if len(tasks) > len(valid_slots) * len(rooms):
        raise ValueError(
            "No complete timetable is possible: not enough room-slot "
            "capacity for all required periods."
        )

    # Keep the existing heuristic: schedule teachers with fewer allowed
    # slots before those with more options.
    def task_priority(task):
        teacher = task["teacher"]
        allowed_slots = normalized_availability.get(teacher, valid_slots)
        return len(allowed_slots)

    tasks.sort(key=task_priority)

    timetable = []

    def backtrack(index):
        if index == len(tasks):
            return True

        task = tasks[index]
        teacher = task["teacher"]
        allowed_slots = normalized_availability.get(teacher, valid_slots)

        for day in days:
            for slot in range(1, slots_per_day + 1):
                if (day, slot) not in allowed_slots:
                    continue

                for room in rooms:
                    candidate = {
                        "day": day,
                        "slot": slot,
                        "subject_id": task["subject_id"],
                        "teacher": teacher,
                        "class_id": task["class_id"],
                        "room": room,
                    }

                    if has_conflict(candidate, timetable):
                        continue

                    timetable.append(candidate)

                    if backtrack(index + 1):
                        return True

                    timetable.pop()

        return False

    if not backtrack(0):
        raise ValueError(
            "No complete timetable is possible with the supplied "
            "teachers, classes, rooms, slots, and availability."
        )

    is_valid, errors = validate_timetable(timetable)

    if not is_valid:
        raise RuntimeError(
            "Internal scheduler error: " + "; ".join(errors)
        )

    return timetable