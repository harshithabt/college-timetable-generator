"""Focused tests for the Flask form and scheduler integration."""

import io
import importlib.util
from pathlib import Path
import re
from html.parser import HTMLParser

import pytest

_APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
_APP_SPEC = importlib.util.spec_from_file_location("flask_web_app", _APP_PATH)
flask_app = importlib.util.module_from_spec(_APP_SPEC)
_APP_SPEC.loader.exec_module(flask_app)


class HiddenInputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("type") == "hidden":
            self.values.setdefault(attributes["name"], []).append(attributes.get("value", ""))


@pytest.fixture
def client():
    flask_app.app.config.update(TESTING=True)
    with flask_app.app.test_client() as test_client:
        yield test_client


def form_data(**overrides):
    data = {
        "days": "Monday, Tuesday",
        "slots_per_day": "2",
        "rooms": "R101, R102",
        "classroom_mode": "automatic",
        "course_code": ["UE24CS341A", "UE24CS341A"],
        "subject_name": ["Database Systems", "Database Systems"],
        "teacher": ["T1", "T2"],
        "class_id": ["CSE-A", "CSE-B"],
        "periods_per_week": ["1", "1"],
    }
    data.update(overrides)
    return data


def test_get_form_page_succeeds(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Fieldnote" in response.data
    assert b"UE24CS341A" in response.data
    assert b"Available classrooms" in response.data
    assert response.get_data(as_text=True).count('name="rooms"') == 1
    assert b'value="automatic" checked' in response.data


def test_valid_manual_submission_shows_official_codes_and_names(client):
    response = client.post("/generate", data=form_data())
    assert response.status_code == 200
    assert b"UE24CS341A" in response.data
    assert b"Database Systems" in response.data
    assert b"Slot 1" in response.data or b"Slot 2" in response.data
    assert b"UE24CS341A_CSEA" not in response.data


def test_assigned_classroom_replaces_scheduler_room_for_every_session():
    timetable = [
        {"class_id": "CSE-A", "room": "scheduler-room", "slot": slot}
        for slot in (1, 2, 3)
    ]
    assigned = flask_app._assign_session_classrooms(timetable, {"CSE-A": "R101"})
    assert [entry["room"] for entry in assigned] == ["R101", "R101", "R101"]


def test_two_sections_with_different_classrooms_can_run_in_same_slot(client):
    data = {
        "days": "Monday",
        "slots_per_day": "1",
        "rooms": "R101, R102",
        "classroom_mode": "automatic",
        "course_code": ["UE24CS341A", "UE24CS341A"],
        "subject_name": ["Database Systems", "Database Systems"],
        "teacher": ["T1", "T2"],
        "class_id": ["CSE-A", "CSE-B"],
        "periods_per_week": ["1", "1"],
    }
    response = client.post("/generate", data=data)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-class-view="0"' in html and 'data-class-view="1"' in html
    assert 'data-classroom="R101"' in html and 'data-classroom="R102"' in html
    assert html.count('class="session-card"') == 2


@pytest.mark.parametrize(
    "assignments, expected",
    [
        ("CSE-A, R101", b"Assign a classroom to every class section"),
        ("CSE-A, R101\nOTHER, R102", b"unknown class section"),
        ("CSE-A, R101\nCSE-B, R101", b"must have its own unique classroom"),
        ("CSE-A, R103\nCSE-B, R102", b"available classroom list"),
        ("CSE-A R101\nCSE-B, R102", b"must be class section, classroom"),
    ],
)
def test_invalid_classroom_assignments_are_rejected(client, assignments, expected):
    response = client.post(
        "/generate", data=form_data(classroom_mode="manual", classroom_assignments=assignments)
    )
    assert response.status_code == 400
    assert expected in response.data


def test_automatic_assignment_fails_when_there_are_too_few_rooms(client):
    response = client.post("/generate", data=form_data(rooms="R101"))
    assert response.status_code == 400
    assert b"needs at least 2 available classrooms" in response.data


def test_manual_classroom_assignment_is_respected(client):
    response = client.post(
        "/generate",
        data=form_data(
            classroom_mode="manual",
            classroom_assignments="CSE-B, R101\nCSE-A, R102",
        ),
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<option value="0" data-classroom="R102">CSE-A</option>' in html
    assert '<option value="1" data-classroom="R101">CSE-B</option>' in html


def test_results_edit_and_regenerate_preserve_manual_configuration(client):
    data = form_data(
        classroom_mode="manual",
        classroom_assignments="CSE-B, R101\nCSE-A, R102",
        availability_enabled="on",
        teacher_availability="T1, Monday, 1",
    )
    results = client.post("/generate", data=data)
    html = results.get_data(as_text=True)
    assert results.status_code == 200
    assert 'formaction="/edit"' in html
    assert 'action="/generate"' in html
    assert "name=\"course_code\"" in html

    parser = HiddenInputs()
    parser.feed(html)
    preserved = parser.values
    assert preserved["classroom_mode"] == ["manual"]
    assert preserved["classroom_assignments"] == ["CSE-B, R101\nCSE-A, R102"]
    assert preserved["availability_enabled"] == ["on"]

    edit = client.post("/edit", data=preserved)
    edit_html = edit.get_data(as_text=True)
    assert edit.status_code == 200
    assert 'value="R101, R102"' in edit_html
    assert "CSE-B, R101\nCSE-A, R102" in edit_html
    assert 'name="availability_enabled"' in edit_html
    assert 'value="UE24CS341A"' in edit_html

    regenerated = client.post("/generate", data=preserved)
    assert regenerated.status_code == 200
    assert 'data-classroom="R102"' in regenerated.get_data(as_text=True)


def test_automatic_colors_match_course_across_sections_and_differ_by_code(client, monkeypatch):
    def fake_scheduler(**kwargs):
        return [
            {"subject_id": subject["subject_id"], "day": "Monday", "slot": slot,
             "class_id": subject["class_id"], "teacher": subject["teacher"], "room": "R101"}
            for slot, subject in enumerate(kwargs["subjects"], start=1)
        ]

    monkeypatch.setattr(flask_app, "generate_timetable", fake_scheduler)
    data = form_data(
        slots_per_day="3",
        course_code=["UE24CS341A", "UE24CS341A", "UE24CS342A"],
        subject_name=["Database Systems", "Database Systems", "Algorithms"],
        teacher=["T1", "T2", "T3"],
        class_id=["CSE-A", "CSE-B", "CSE-A"],
        periods_per_week=["1", "1", "1"],
    )
    response = client.post("/generate", data=data)
    assert response.status_code == 200
    colors = re.findall(
        r'class="session-card" style="--subject-color: (#[0-9A-F]{6})"',
        response.get_data(as_text=True),
    )
    assert len(colors) == 3
    assert colors[0] == colors[2]
    assert colors[0] != colors[1]


def test_manual_color_is_used_for_same_course_in_each_section(client, monkeypatch):
    def fake_scheduler(**kwargs):
        return [
            {"subject_id": subject["subject_id"], "day": "Monday", "slot": slot,
             "class_id": subject["class_id"], "teacher": subject["teacher"], "room": "R101"}
            for slot, subject in enumerate(kwargs["subjects"], start=1)
        ]

    monkeypatch.setattr(flask_app, "generate_timetable", fake_scheduler)
    data = form_data(
        color_mode="manual",
        course_code=["UE24CS341A", "UE24CS341A"],
        subject_name=["Database Systems", "Database Systems"],
        teacher=["T1", "T2"],
        class_id=["CSE-A", "CSE-B"],
        periods_per_week=["1", "1"],
        subject_color=["#AABBCC", "#AABBCC"],
    )
    response = client.post("/generate", data=data)
    assert response.status_code == 200
    assert response.get_data(as_text=True).count(
        'style="--subject-color: #AABBCC"'
    ) == 2


def test_manual_colors_for_same_course_must_match(client):
    data = form_data(
        color_mode="manual",
        subject_color=["#AABBCC", "#DDEEFF"],
    )
    response = client.post("/generate", data=data)
    assert response.status_code == 400
    assert b"Use the same color for course code" in response.data


def test_theme_controls_and_styles_are_available(client):
    for page in (client.get("/"), client.post("/generate", data=form_data())):
        assert page.status_code == 200
        assert b"data-theme-toggle" in page.data
        assert b"college-timetable-theme" in page.data
    css = client.get("/static/style.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200
    assert b':root[data-theme="dark"]' in css.data
    assert b".table-wrap { overflow-x: auto" in css.data
    assert b"@media (max-width" in css.data
    assert js.status_code == 200
    assert b"prefers-color-scheme" not in js.data  # preference is applied before CSS in the templates
    assert b"localStorage.setItem" in js.data
    assert b"data-selected-classroom" in js.data
    assert b"form.dataset.submitting" in js.data


def test_csv_template_download(client):
    response = client.get("/subjects-template.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data.decode().strip() == "course_code,subject_name,teacher,class_id,periods_per_week"


def test_valid_csv_upload(client):
    content = "course_code,subject_name,teacher,class_id,periods_per_week\nUE24CS341A,Database Systems,T1,CSE-A,1\n"
    data = {
        "days": "Monday",
        "slots_per_day": "1",
        "rooms": "R101",
        "subjects_csv": (io.BytesIO(content.encode()), "subjects.csv"),
    }
    response = client.post("/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    assert b"UE24CS341A" in response.data
    assert b"Database Systems" in response.data


def test_csv_and_manual_rows_cannot_be_mixed(client):
    data = form_data()
    data["subjects_csv"] = (io.BytesIO(b""), "subjects.csv")
    response = client.post("/generate", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert b"either the CSV upload or manual subject rows" in response.data


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"days": ""}, b"Enter at least one day"),
        ({"classroom_mode": "manual", "classroom_assignments": "CSE-A, R101\nCSE-B, R101"}, b"unique classroom"),
        ({"slots_per_day": "zero"}, b"positive whole number"),
        ({"periods_per_week": ["0", "1"]}, b"positive whole number"),
        ({"teacher": ["", "T2"]}, b"teacher is required"),
    ],
)
def test_invalid_manual_inputs_are_rejected_cleanly(client, overrides, expected):
    response = client.post("/generate", data=form_data(**overrides))
    assert response.status_code == 400
    assert expected in response.data
    assert b"Traceback" not in response.data


def test_validation_errors_identify_subject_row_and_preserve_values(client):
    data = form_data(teacher=["", "T2"])
    response = client.post("/generate", data=data)
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert b"Subject row 1: teacher is required" in response.data
    assert b"Check subject row 1" in response.data
    assert html.count('value="UE24CS341A"') >= 2
    assert 'value="T2"' in html


def test_invalid_csv_headers_and_malformed_rows_are_rejected(client):
    for content, expected in [
        ("wrong,headers\nA,B\n", b"CSV headers must be"),
        ("course_code,subject_name,teacher,class_id,periods_per_week\nA,B,T1,C1\n", b"wrong number of columns"),
        ("course_code,subject_name,teacher,class_id,periods_per_week\nA,B,T1,C1,nope\n", b"positive whole number"),
        ("course_code,subject_name,teacher,class_id,periods_per_week\n", b"no data rows"),
    ]:
        data = {
            "days": "Monday",
            "slots_per_day": "2",
            "rooms": "R101",
            "subjects_csv": (io.BytesIO(content.encode()), "subjects.csv"),
        }
        response = client.post("/generate", data=data, content_type="multipart/form-data")
        assert response.status_code == 400
        assert expected in response.data


def test_duplicate_normalized_offering_ids_get_unique_safe_ids(client, monkeypatch):
    captured = {}

    def fake_scheduler(**kwargs):
        captured.update(kwargs)
        return [
            {"subject_id": subject["subject_id"], "day": "Monday", "slot": index,
             "class_id": subject["class_id"], "teacher": subject["teacher"], "room": "R101"}
            for index, subject in enumerate(kwargs["subjects"], start=1)
        ]

    monkeypatch.setattr(flask_app, "generate_timetable", fake_scheduler)
    data = form_data(
        course_code=["UE24CS341A", "UE24CS341A"],
        subject_name=["Database Systems", "Databases II"],
        teacher=["T1", "T2"],
        class_id=["CSE-A", "CSE-A"],
        periods_per_week=["1", "1"],
    )
    response = client.post("/generate", data=data)
    assert response.status_code == 200
    ids = [subject["subject_id"] for subject in captured["subjects"]]
    assert ids == ["UE24CS341A_CSEA", "UE24CS341A_CSEA_2"]
    assert response.get_data(as_text=True).count(
        'class="course-code">UE24CS341A'
    ) == 2
    assert b"Databases II" in response.data


def test_scheduler_value_error_is_friendly(client, monkeypatch):
    def fail(**_kwargs):
        raise ValueError("No complete timetable is possible.")

    monkeypatch.setattr(flask_app, "generate_timetable", fail)
    response = client.post("/generate", data=form_data())
    assert response.status_code == 400
    assert b"No complete timetable is possible" in response.data
    assert b"Traceback" not in response.data


def test_teacher_availability_is_converted_to_one_based_slots(client, monkeypatch):
    captured = {}

    def fake_scheduler(**kwargs):
        captured.update(kwargs)
        subject = kwargs["subjects"][0]
        return [{"subject_id": subject["subject_id"], "day": "Tuesday", "slot": 2,
                 "class_id": subject["class_id"], "teacher": subject["teacher"], "room": "R101"}]

    monkeypatch.setattr(flask_app, "generate_timetable", fake_scheduler)
    data = {
        "days": "Monday, Tuesday",
        "slots_per_day": "2",
        "rooms": "R101",
        "course_code": "UE24CS341A",
        "subject_name": "Database Systems",
        "teacher": "T1",
        "class_id": "CSE-A",
        "periods_per_week": "1",
        "availability_enabled": "on",
        "teacher_availability": "T1, Tuesday, 2",
    }
    response = client.post("/generate", data=data)
    assert response.status_code == 200
    assert captured["teacher_availability"] == {"T1": {("Tuesday", 2)}}
    assert b"Slot 2" in response.data


def test_disabled_teacher_availability_passes_none(client, monkeypatch):
    captured = {}

    def fake_scheduler(**kwargs):
        captured.update(kwargs)
        subject = kwargs["subjects"][0]
        return [{"subject_id": subject["subject_id"], "day": "Monday", "slot": 1,
                 "class_id": subject["class_id"], "teacher": subject["teacher"], "room": "R101"}]

    monkeypatch.setattr(flask_app, "generate_timetable", fake_scheduler)
    data = {
        "days": "Monday",
        "slots_per_day": "1",
        "rooms": "R101",
        "course_code": "UE24CS341A",
        "subject_name": "Database Systems",
        "teacher": "T1",
        "class_id": "CSE-A",
        "periods_per_week": "1",
    }
    response = client.post("/generate", data=data)
    assert response.status_code == 200
    assert captured["teacher_availability"] is None


@pytest.mark.parametrize(
    "line, expected",
    [
        ("UNKNOWN, Monday, 1", b"unknown teacher"),
        ("T1, Friday, 1", b"unknown day"),
        ("T1, Monday, 3", b"slot must be between 1 and 2"),
        ("T1, Monday, not-a-number", b"positive whole number"),
    ],
)
def test_invalid_teacher_availability_is_rejected(client, line, expected):
    data = {
        "days": "Monday, Tuesday",
        "slots_per_day": "2",
        "rooms": "R101",
        "course_code": "UE24CS341A",
        "subject_name": "Database Systems",
        "teacher": "T1",
        "class_id": "CSE-A",
        "periods_per_week": "1",
        "availability_enabled": "on",
        "teacher_availability": line,
    }
    response = client.post("/generate", data=data)
    assert response.status_code == 400
    assert expected in response.data
