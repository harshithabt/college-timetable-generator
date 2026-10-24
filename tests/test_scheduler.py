"""Automated tests for timetable constraints and scheduling."""

import pytest

from app.constraints import has_conflict, validate_timetable
from app.scheduler import generate_timetable


def entry(day="Monday", slot=1, teacher="T1", class_id="C1", room="R101"):
    return {
        "day": day,
        "slot": slot,
        "teacher": teacher,
        "class_id": class_id,
        "room": room,
    }


def simple_subjects():
    return [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 1,
        }
    ]


def test_no_conflict_for_different_slot():
    assert has_conflict(entry(slot=2), [entry(slot=1)]) is False


def test_detects_teacher_clash():
    candidate = entry(class_id="C2", room="R102")
    assert has_conflict(candidate, [entry()]) is True


def test_detects_class_clash():
    candidate = entry(teacher="T2", room="R102")
    assert has_conflict(candidate, [entry()]) is True


def test_detects_room_clash():
    candidate = entry(teacher="T2", class_id="C2")
    assert has_conflict(candidate, [entry()]) is True


def test_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="missing fields"):
        has_conflict({"day": "Monday"}, [])


def test_validates_conflict_free_timetable():
    timetable = [
        entry(teacher="T1", class_id="C1", room="R101"),
        entry(teacher="T2", class_id="C2", room="R102"),
    ]

    is_valid, errors = validate_timetable(timetable)

    assert is_valid is True
    assert errors == []


def test_generates_complete_timetable():
    subjects = [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 2,
        },
        {
            "subject_id": "PHY",
            "teacher": "T2",
            "class_id": "C1",
            "periods_per_week": 1,
        },
        {
            "subject_id": "CS",
            "teacher": "T1",
            "class_id": "C2",
            "periods_per_week": 2,
        },
    ]

    timetable = generate_timetable(
        subjects=subjects,
        rooms=["R101", "R102"],
        days=["Monday", "Tuesday"],
        slots_per_day=3,
    )

    assert len(timetable) == 5

    for subject in subjects:
        count = sum(
            item["subject_id"] == subject["subject_id"]
            for item in timetable
        )
        assert count == subject["periods_per_week"]

    is_valid, errors = validate_timetable(timetable)
    assert is_valid is True, errors


def test_respects_teacher_availability():
    timetable = generate_timetable(
        subjects=simple_subjects(),
        rooms=["R101"],
        days=["Monday", "Tuesday"],
        slots_per_day=2,
        teacher_availability={"T1": {("Tuesday", 2)}},
    )

    assert timetable[0]["day"] == "Tuesday"
    assert timetable[0]["slot"] == 2


def test_raises_error_when_no_complete_timetable_exists():
    subjects = [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 2,
        }
    ]

    with pytest.raises(ValueError, match="No complete timetable"):
        generate_timetable(
            subjects=subjects,
            rooms=["R101"],
            days=["Monday"],
            slots_per_day=1,
        )


def test_rejects_duplicate_subject_ids():
    subjects = [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 1,
        },
        {
            "subject_id": "MATH",
            "teacher": "T2",
            "class_id": "C2",
            "periods_per_week": 1,
        },
    ]

    with pytest.raises(ValueError, match="Duplicate subject ID"):
        generate_timetable(
            subjects=subjects,
            rooms=["R101"],
            days=["Monday"],
            slots_per_day=2,
        )


def test_rejects_two_subjects_for_same_class_in_one_slot():
    subjects = [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 1,
        },
        {
            "subject_id": "PHY",
            "teacher": "T2",
            "class_id": "C1",
            "periods_per_week": 1,
        },
    ]

    with pytest.raises(ValueError, match="No complete timetable"):
        generate_timetable(
            subjects=subjects,
            rooms=["R101", "R102"],
            days=["Monday"],
            slots_per_day=1,
        )


@pytest.mark.parametrize(
    "invalid_pair",
    [
        ("Monday", []),
        ("Monday", 0),
        ("Monday", -1),
        ("Monday", True),
        ("Monday", False),
        ("Monday", "first"),
        ("Monday", None),
        ("Funday", 1),
        ([], 1),
        ("Monday", 4),
        ("", 1),
    ],
)
def test_rejects_malformed_teacher_availability(invalid_pair):
    # A list is intentional: it permits unhashable malformed pairs such
    # as ("Monday", []) to reach the validation code.
    with pytest.raises(ValueError):
        generate_timetable(
            subjects=simple_subjects(),
            rooms=["R101"],
            days=["Monday", "Tuesday"],
            slots_per_day=3,
            teacher_availability={"T1": [invalid_pair]},
        )


def test_rejects_malformed_availability_pair_length():
    with pytest.raises(ValueError, match="Invalid availability entry"):
        generate_timetable(
            subjects=simple_subjects(),
            rooms=["R101"],
            days=["Monday"],
            slots_per_day=2,
            teacher_availability={"T1": [("Monday",)]},
        )


def test_rejects_invalid_availability_collection():
    with pytest.raises(ValueError, match="must be a collection"):
        generate_timetable(
            subjects=simple_subjects(),
            rooms=["R101"],
            days=["Monday"],
            slots_per_day=2,
            teacher_availability={"T1": "Monday"},
        )


def test_accepts_valid_teacher_availability_pair():
    timetable = generate_timetable(
        subjects=simple_subjects(),
        rooms=["R101"],
        days=["Monday", "Tuesday"],
        slots_per_day=3,
        teacher_availability={"T1": [("Tuesday", 2)]},
    )

    assert len(timetable) == 1
    assert timetable[0]["day"] == "Tuesday"
    assert timetable[0]["slot"] == 2


@pytest.mark.parametrize("invalid_slot", [0, -1, True, False, "first", None, 1.5])
def test_validator_rejects_invalid_slot_values(invalid_slot):
    is_valid, errors = validate_timetable([entry(slot=invalid_slot)])

    assert is_valid is False
    assert errors
    assert any("Slot must be a positive integer" in error for error in errors)


def test_validator_rejects_invalid_slot_even_in_single_entry():
    # No pairwise comparisons are possible with a one-entry timetable.
    # Its own fields must still be validated.
    is_valid, errors = validate_timetable([entry(slot=True)])

    assert is_valid is False
    assert errors


def test_has_conflict_rejects_invalid_candidate_slot():
    with pytest.raises(ValueError, match="Slot must be a positive integer"):
        has_conflict(entry(slot=True), [])


def test_generate_timetable_rejects_boolean_slots_per_day():
    with pytest.raises(ValueError, match="slots_per_day"):
        generate_timetable(
            subjects=simple_subjects(),
            rooms=["R101"],
            days=["Monday"],
            slots_per_day=True,
        )


def test_availability_validation_does_not_mutate_input():
    availability = {"T1": [("Tuesday", 2)]}
    original = {"T1": [("Tuesday", 2)]}

    generate_timetable(
        subjects=simple_subjects(),
        rooms=["R101"],
        days=["Monday", "Tuesday"],
        slots_per_day=2,
        teacher_availability=availability,
    )

    assert availability == original