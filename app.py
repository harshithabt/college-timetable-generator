"""Flask interface for the college timetable scheduler."""

import csv
import colorsys
import io
import re
from collections import defaultdict

from flask import Flask, make_response, render_template, request

from app.constraints import validate_timetable
from app.scheduler import generate_timetable


app = Flask(__name__)

CSV_HEADERS = (
    "course_code",
    "subject_name",
    "teacher",
    "class_id",
    "periods_per_week",
)
SUBJECT_COLOR_PALETTE = (
    "#A6BBA4", "#82977A", "#9BB9CA", "#D1AE70",
    "#B0A6C8", "#CB9BA2", "#C38769", "#85AAA2",
    "#C2B279", "#899FB7", "#9FB5AD", "#AC8FA3",
    "#77917F", "#879CB0", "#D0A27F", "#B5A2B7",
)


def _split_list(value, label):
    """Parse a comma-separated list and reject empty or repeated values."""
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise ValueError(f"Enter at least one {label}.")
    if len(items) != len(set(items)):
        raise ValueError(f"{label.capitalize()} must not contain duplicates.")
    return items


def _parse_classrooms(raw, class_ids, available_rooms):
    """Parse and validate one manual room assignment per class section."""
    classrooms = {}
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"Classroom line {line_number} must be class section, classroom."
            )
        class_id, room = parts
        if class_id in classrooms:
            raise ValueError(f"Class section '{class_id}' has more than one classroom assignment.")
        classrooms[class_id] = room

    missing = [class_id for class_id in class_ids if class_id not in classrooms]
    unknown = [class_id for class_id in classrooms if class_id not in class_ids]
    if unknown:
        raise ValueError(
            "Classroom assignments include unknown class section(s): "
            + ", ".join(unknown) + "."
        )
    if missing:
        raise ValueError(
            "Assign a classroom to every class section. Missing: "
            + ", ".join(missing) + "."
        )
    if len(set(classrooms.values())) != len(classrooms):
        raise ValueError("Each class section must have its own unique classroom.")
    invalid_rooms = [room for room in classrooms.values() if room not in available_rooms]
    if invalid_rooms:
        raise ValueError(
            "Classroom assignments must use rooms in the available classroom list: "
            + ", ".join(invalid_rooms) + "."
        )
    return classrooms


def _resolve_classrooms(class_ids, available_rooms, mode, raw_manual_assignments):
    """Return the one fixed room for each class in automatic or manual mode."""
    if mode == "automatic":
        if len(available_rooms) < len(class_ids):
            raise ValueError(
                f"Automatic assignment needs at least {len(class_ids)} available "
                f"classrooms for {len(class_ids)} class sections."
            )
        return dict(zip(class_ids, available_rooms))
    if mode == "manual":
        return _parse_classrooms(raw_manual_assignments, class_ids, available_rooms)
    raise ValueError("Choose automatic or manual classroom assignment.")


def _default_form_values():
    return {
        "days": "Monday, Tuesday, Wednesday, Thursday, Friday",
        "slots_per_day": "6",
        "rooms": "R101, R102, R103, R104",
        "classroom_mode": "automatic",
        "classroom_assignments": "",
        "color_mode": "auto",
        "availability_enabled": False,
        "teacher_availability": "",
    }


def _form_values(form):
    values = _default_form_values()
    values.update({
        "days": form.get("days", values["days"]),
        "slots_per_day": form.get("slots_per_day", values["slots_per_day"]),
        "rooms": form.get("rooms", values["rooms"]),
        "classroom_mode": form.get("classroom_mode", "automatic"),
        "classroom_assignments": form.get("classroom_assignments", ""),
        "color_mode": form.get("color_mode", "auto"),
        "availability_enabled": form.get("availability_enabled") == "on",
        "teacher_availability": form.get("teacher_availability", ""),
    })
    return values


def _form_subject_rows(form):
    """Keep typed subject values visible after validation errors or Edit."""
    fields = ("course_code", "subject_name", "teacher", "class_id", "periods_per_week")
    columns = {
        field: form.getlist(field) if hasattr(form, "getlist") else []
        for field in fields
    }
    count = max((len(values) for values in columns.values()), default=0)
    colors = form.getlist("subject_color") if hasattr(form, "getlist") else []
    rows = []
    for index in range(count):
        rows.append({
            **{field: columns[field][index] if index < len(columns[field]) else ""
               for field in fields},
            "subject_color": colors[index] if index < len(colors) else SUBJECT_COLOR_PALETTE[0],
        })
    return rows or [{
        "course_code": "", "subject_name": "", "teacher": "", "class_id": "",
        "periods_per_week": "3", "subject_color": SUBJECT_COLOR_PALETTE[0],
    }]


def _render_index(error=None, form_values=None, subject_rows=None):
    error_row = None
    error_target = None
    if error:
        csv_row = re.search(r"CSV row (\d+)", error, re.IGNORECASE)
        subject_row = re.search(r"Subject row (\d+)", error, re.IGNORECASE)
        if csv_row:
            error_row = max(0, int(csv_row.group(1)) - 2)
            error_target = "subjects"
        elif subject_row:
            error_row = int(subject_row.group(1)) - 1
            error_target = "subjects"
        elif "day" in error.lower():
            error_target = "days"
        elif "slots per day" in error.lower():
            error_target = "slots_per_day"
        elif "classroom" in error.lower() or "room" in error.lower():
            error_target = "classroom_assignments" if "assignment" in error.lower() else "rooms"
        elif "availability" in error.lower():
            error_target = "teacher_availability"
        elif "subject" in error.lower() or "csv" in error.lower():
            error_target = "subjects"
    return render_template(
        "index.html",
        error=error,
        error_target=error_target,
        error_row=error_row,
        form_values=form_values or _default_form_values(),
        subject_rows=subject_rows or _form_subject_rows({}),
        subject_color_palette=SUBJECT_COLOR_PALETTE,
    )


def _assign_session_classrooms(timetable, classrooms):
    """Replace scheduler-selected rooms with each section's fixed room."""
    try:
        return [
            {**entry, "room": classrooms[entry["class_id"]]}
            for entry in timetable
        ]
    except KeyError as exc:
        raise ValueError(
            f"The scheduler returned a session for an unassigned class section: {exc.args[0]}."
        ) from None


def _positive_integer(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive whole number.") from None
    if number < 1 or str(number) != str(value).strip():
        raise ValueError(f"{label} must be a positive whole number.")
    return number


def _internal_subject_ids(rows):
    """Assign stable, unique IDs while preserving official codes separately."""
    counts = defaultdict(int)
    used = set()
    for row in rows:
        course_part = re.sub(r"[^A-Za-z0-9]", "", row["course_code"]).upper()
        section_part = re.sub(r"[^A-Za-z0-9]", "", row["class_id"]).upper()
        base = f"{course_part}_{section_part}".strip("_") or "SUBJECT"
        counts[base] += 1
        candidate = base if counts[base] == 1 else f"{base}_{counts[base]}"
        while candidate in used:
            counts[base] += 1
            candidate = f"{base}_{counts[base]}"
        used.add(candidate)
        row["subject_id"] = candidate
    return rows


def _read_subject_rows(form, files):
    """Read either an uploaded CSV or the manual subject table."""
    upload = files.get("subjects_csv")
    if upload and upload.filename:
        if any(form.get(key, "").strip() for key in ("course_code", "subject_name", "teacher", "class_id", "periods_per_week")):
            raise ValueError("Use either the CSV upload or manual subject rows, not both.")
        try:
            content = upload.stream.read().decode("utf-8-sig")
        except (UnicodeDecodeError, OSError):
            raise ValueError("The uploaded CSV must be a readable UTF-8 file.") from None
        if not content.strip():
            raise ValueError("The uploaded CSV is empty.")
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None or tuple(name.strip() for name in reader.fieldnames) != CSV_HEADERS:
            raise ValueError("CSV headers must be: " + ", ".join(CSV_HEADERS) + ".")
        rows = []
        for line_number, values in enumerate(reader, start=2):
            if None in values or any(value is None for value in values.values()):
                raise ValueError(f"CSV row {line_number} has the wrong number of columns.")
            rows.append({key: (values[key] or "").strip() for key in CSV_HEADERS})
    else:
        fields = ("course_code", "subject_name", "teacher", "class_id", "periods_per_week")
        columns = {field: form.getlist(field) for field in fields}
        if not any(value.strip() for field_values in columns.values() for value in field_values):
            raise ValueError("Add at least one subject offering or upload a CSV.")
        if len({len(values) for values in columns.values()}) != 1:
            raise ValueError("Subject rows are incomplete. Please check the form and try again.")
        submitted_colors = form.getlist("subject_color")
        if submitted_colors and len(submitted_colors) != len(columns["course_code"]):
            raise ValueError("Subject color settings do not match the subject rows.")
        rows = [
            {
                **{field: columns[field][index].strip() for field in fields},
                "subject_color": submitted_colors[index]
                if submitted_colors else SUBJECT_COLOR_PALETTE[0],
            }
            for index in range(len(columns["course_code"]))
        ]

    if not rows:
        raise ValueError("The subject list contains no data rows.")
    for number, row in enumerate(rows, start=1):
        for field in CSV_HEADERS[:-1]:
            if not row[field]:
                raise ValueError(f"Subject row {number}: {field.replace('_', ' ')} is required.")
        row["periods_per_week"] = _positive_integer(
            row["periods_per_week"], f"Periods per week in subject row {number}"
        )
    return _internal_subject_ids(rows)


def _assign_subject_colors(rows, color_mode):
    """Apply deterministic per-course colours or validated manual colours."""
    if color_mode == "auto":
        course_codes = sorted({row["course_code"] for row in rows})
        colors = {}
        for index, code in enumerate(course_codes):
            if index < len(SUBJECT_COLOR_PALETTE):
                colors[code] = SUBJECT_COLOR_PALETTE[index]
            else:
                hue = (index * 137.508) % 360
                red, green, blue = colorsys.hls_to_rgb(hue / 360, 0.68, 0.26)
                colors[code] = "#{:02X}{:02X}{:02X}".format(
                    round(red * 255), round(green * 255), round(blue * 255)
                )
        for row in rows:
            row["subject_color"] = colors[row["course_code"]]
        return

    colors_by_course = {}
    for row in rows:
        color = row["subject_color"].strip().upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            raise ValueError("Choose a valid color for every subject offering.")
        course_code = row["course_code"]
        previous_color = colors_by_course.get(course_code)
        if previous_color and previous_color != color:
            raise ValueError(
                f"Use the same color for course code '{course_code}' in every section."
            )
        colors_by_course[course_code] = color

    for row in rows:
        row["subject_color"] = colors_by_course[row["course_code"]]


def _parse_availability(raw, teachers, days, slots_per_day):
    """Parse optional lines formatted as teacher,day,slot."""
    availability = defaultdict(set)
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"Availability line {line_number} must be teacher, day, slot.")
        teacher, day, slot_text = parts
        if teacher not in teachers:
            raise ValueError(f"Availability line {line_number} names an unknown teacher: {teacher}.")
        if day not in days:
            raise ValueError(f"Availability line {line_number} names an unknown day: {day}.")
        slot = _positive_integer(slot_text, f"Slot on availability line {line_number}")
        if slot > slots_per_day:
            raise ValueError(f"Availability line {line_number}: slot must be between 1 and {slots_per_day}.")
        availability[teacher].add((day, slot))
    return dict(availability)


@app.get("/")
def index():
    return _render_index()


@app.post("/edit")
def edit_settings():
    """Return to the configuration form with the current settings restored."""
    return _render_index(
        form_values=_form_values(request.form),
        subject_rows=_form_subject_rows(request.form),
    )


@app.get("/subjects-template.csv")
def download_csv_template():
    response = make_response(",".join(CSV_HEADERS) + "\n")
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=subjects-template.csv"
    return response


@app.post("/generate")
def generate():
    rows = []
    try:
        days = _split_list(request.form.get("days", ""), "day")
        rooms = _split_list(request.form.get("rooms", ""), "classroom")
        slots_per_day = _positive_integer(request.form.get("slots_per_day"), "Slots per day")
        upload = request.files.get("subjects_csv")
        is_csv_upload = bool(upload and upload.filename)
        rows = _read_subject_rows(request.form, request.files)
        class_ids = list(dict.fromkeys(row["class_id"] for row in rows))
        classroom_mode = request.form.get("classroom_mode", "automatic")
        classrooms = _resolve_classrooms(
            class_ids, rooms, classroom_mode,
            request.form.get("classroom_assignments", ""),
        )
        color_mode = request.form.get("color_mode", "auto")
        if color_mode not in {"auto", "manual"}:
            raise ValueError("Choose automatic or manual subject colors.")
        _assign_subject_colors(rows, "auto" if is_csv_upload else color_mode)
        subjects = [
            {
                "subject_id": row["subject_id"],
                "teacher": row["teacher"],
                "class_id": row["class_id"],
                "periods_per_week": row["periods_per_week"],
            }
            for row in rows
        ]
        availability = None
        if request.form.get("availability_enabled") == "on":
            teachers = {subject["teacher"] for subject in subjects}
            availability = _parse_availability(
                request.form.get("teacher_availability", ""), teachers, days, slots_per_day
            )

        timetable = generate_timetable(
            subjects=subjects,
            rooms=rooms,
            days=days,
            slots_per_day=slots_per_day,
            teacher_availability=availability,
        )
        timetable = _assign_session_classrooms(timetable, classrooms)
        is_valid, conflict_errors = validate_timetable(timetable)
        if not is_valid:
            raise ValueError(
                "The fixed classroom assignments conflict with the generated "
                "timetable: " + "; ".join(conflict_errors)
            )
    except ValueError as exc:
        return _render_index(
            error=str(exc),
            form_values=_form_values(request.form),
            subject_rows=rows or _form_subject_rows(request.form),
        ), 400

    offerings = {row["subject_id"]: row for row in rows}
    day_order = {day: index for index, day in enumerate(days)}
    timetable.sort(key=lambda entry: (day_order[entry["day"]], entry["slot"], entry["class_id"]))
    display_rows = [
        {**entry,
         "course_code": offerings[entry["subject_id"]]["course_code"],
         "subject_name": offerings[entry["subject_id"]]["subject_name"],
         "subject_color": offerings[entry["subject_id"]]["subject_color"]}
        for entry in timetable
    ]
    slots = range(1, slots_per_day + 1)
    grid = {
        class_id: {
            day: {slot: [] for slot in slots}
            for day in days
        }
        for class_id in class_ids
    }
    for entry in display_rows:
        grid[entry["class_id"]][entry["day"]][entry["slot"]].append(entry)

    settings = _form_values(request.form)
    settings["rooms"] = ", ".join(rooms)
    settings["color_mode"] = "auto" if is_csv_upload else color_mode
    return render_template(
        "results.html",
        timetable=display_rows,
        days=days,
        slots=slots,
        class_ids=class_ids,
        classrooms=classrooms,
        grid=grid,
        settings=settings,
        subject_rows=rows,
    )


if __name__ == "__main__":
    app.run(debug=True)
