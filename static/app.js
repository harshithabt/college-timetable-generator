"use strict";

const root = document.documentElement;

function updateThemeButton(button, theme) {
  const nextIsDark = theme !== "dark";
  button.setAttribute("aria-label", nextIsDark ? "Switch to dark theme" : "Switch to light theme");
  button.querySelector("[data-theme-icon]").textContent = nextIsDark ? "☾" : "☀";
  button.querySelector("[data-theme-label]").textContent = nextIsDark ? "Dark" : "Light";
}

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  updateThemeButton(button, root.dataset.theme || "light");
  button.addEventListener("click", () => {
    const theme = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = theme;
    try { localStorage.setItem("college-timetable-theme", theme); } catch (_) { /* Page theme still changes. */ }
    updateThemeButton(button, theme);
  });
});

const classSelector = document.getElementById("class-selector");
if (classSelector) {
  const classViews = document.querySelectorAll(".class-view");
  const classroomLabel = document.querySelector("[data-selected-classroom]");
  const showSelectedClass = () => {
    classViews.forEach((view) => { view.hidden = view.dataset.classView !== classSelector.value; });
    const selected = classSelector.selectedOptions[0];
    if (classroomLabel && selected) classroomLabel.textContent = selected.dataset.classroom;
  };
  classSelector.addEventListener("change", showSelectedClass);
  showSelectedClass();
}

const subjectRows = document.getElementById("subjects");
if (subjectRows) {
  const colorModeRadios = document.querySelectorAll('input[name="color_mode"]');
  const manualColors = document.querySelector('input[name="color_mode"][value="manual"]');
  const autoColors = document.querySelector('input[name="color_mode"][value="auto"]');
  const csvInput = document.getElementById("subjects_csv");
  const classroomModeRadios = document.querySelectorAll('input[name="classroom_mode"]');
  const manualClassrooms = document.querySelector('input[name="classroom_mode"][value="manual"]');
  const manualClassroomLabel = document.getElementById("manual-classroom-label");
  const manualClassroomInput = document.getElementById("classroom_assignments");
  const assignmentNote = document.querySelector("[data-assignment-note]");
  const roomList = document.querySelector('input[name="rooms"]');

  function updateColorControls() {
    const manual = manualColors.checked && !manualColors.disabled;
    subjectRows.querySelectorAll(".subject-color-input").forEach((input) => {
      input.hidden = !manual;
      input.tabIndex = manual ? 0 : -1;
    });
    subjectRows.querySelectorAll(".auto-color-note").forEach((note) => { note.hidden = manual; });
  }

  function updateClassroomControls() {
    const manual = manualClassrooms.checked;
    manualClassroomLabel.hidden = !manual;
    manualClassroomInput.required = manual;
    const sections = new Set(Array.from(subjectRows.rows)
      .map((row) => row.querySelector('[name="class_id"]').value.trim()).filter(Boolean));
    const available = roomList.value.split(",").map((room) => room.trim()).filter(Boolean);
    if (manual) {
      assignmentNote.textContent = "Manual mode requires one assignment per section, using a room from the available list.";
    } else if (sections.size > available.length) {
      assignmentNote.textContent = `There are ${sections.size} sections but only ${available.length} available classrooms.`;
    } else {
      assignmentNote.textContent = `Automatic mode assigns one of the ${available.length} available classrooms to each of the ${sections.size} section${sections.size === 1 ? "" : "s"}, in subject-table order.`;
    }
  }

  colorModeRadios.forEach((radio) => radio.addEventListener("change", updateColorControls));
  classroomModeRadios.forEach((radio) => radio.addEventListener("change", updateClassroomControls));
  roomList.addEventListener("input", updateClassroomControls);
  subjectRows.addEventListener("input", (event) => {
    if (event.target.matches('[name="class_id"]')) updateClassroomControls();
  });

  csvInput.addEventListener("change", () => {
    const csvSelected = Boolean(csvInput.files.length);
    manualColors.disabled = csvSelected;
    if (csvSelected) autoColors.checked = true;
    subjectRows.querySelectorAll("input").forEach((input) => { input.disabled = csvSelected; });
    updateColorControls();
  });

  subjectRows.addEventListener("click", (event) => {
    const remove = event.target.closest(".remove-row");
    if (remove && subjectRows.rows.length > 1) {
      remove.closest("tr").remove();
      updateClassroomControls();
    }
  });

  subjectRows.addEventListener("change", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    if (event.target.matches(".subject-color-input")) {
      const code = row.querySelector('[name="course_code"]').value.trim();
      if (code) subjectRows.querySelectorAll("tr").forEach((otherRow) => {
        if (otherRow.querySelector('[name="course_code"]').value.trim() === code) {
          otherRow.querySelector(".subject-color-input").value = event.target.value;
        }
      });
    }
    if (event.target.matches('[name="course_code"]')) {
      const code = event.target.value.trim();
      const sibling = Array.from(subjectRows.rows).find((otherRow) =>
        otherRow !== row && otherRow.querySelector('[name="course_code"]').value.trim() === code);
      if (sibling && code) row.querySelector(".subject-color-input").value = sibling.querySelector(".subject-color-input").value;
    }
  });

  document.getElementById("add-row").addEventListener("click", () => {
    const row = subjectRows.rows[0].cloneNode(true);
    row.querySelectorAll("input").forEach((input) => {
      input.disabled = false;
      if (input.name === "periods_per_week") input.value = "1";
      else if (input.type === "color") input.value = "#A6BBA4";
      else input.value = "";
    });
    subjectRows.appendChild(row);
    updateColorControls();
    updateClassroomControls();
    row.querySelector('[name="course_code"]').focus();
  });

  const availabilityToggle = document.getElementById("availability-toggle");
  availabilityToggle.addEventListener("change", () => {
    document.getElementById("availability-fields").hidden = !availabilityToggle.checked;
  });
  updateColorControls();
  updateClassroomControls();
}

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    const button = event.submitter;
    if (button && button.matches("[data-submit-button]")) {
      button.disabled = true;
      if (button.formAction.endsWith("/generate")) button.textContent = "Generating…";
    }
  });
});
