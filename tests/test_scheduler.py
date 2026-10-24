
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


def test_no_conflict_for_different_slot():
    candidate = entry(slot=2)
    assert has_conflict(candidate, [entry(slot=1)]) is False


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
        entry(day="Monday", slot=1, teacher="T1", class_id="C1", room="R101"),
        entry(day="Monday", slot=1, teacher="T2", class_id="C2", room="R102"),
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
        scheduled_count = sum(
            item["subject_id"] == subject["subject_id"]
            for item in timetable
        )
        assert scheduled_count == subject["periods_per_week"]

    is_valid, errors = validate_timetable(timetable)
    assert is_valid is True, errors


def test_respects_teacher_availability():
    subjects = [
        {
            "subject_id": "MATH",
            "teacher": "T1",
            "class_id": "C1",
            "periods_per_week": 1,
        }
    ]

    timetable = generate_timetable(
        subjects=subjects,
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
