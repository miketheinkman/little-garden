const repeatSchedule = document.querySelector("#id_repeat");
function showScheduleFields() {
  document.querySelector("[data-weekdays]").hidden = repeatSchedule.value !== "weekly";
  document.querySelector("#id_end").disabled = repeatSchedule.value === "once";
  document.querySelector("[data-end]").hidden = repeatSchedule.value === "once";
  document.querySelector("[data-repeat-note]").hidden = repeatSchedule.value === "once";
}
repeatSchedule.addEventListener("change", showScheduleFields);
showScheduleFields();

const dayPicker = document.querySelector("[data-weekdays]");
dayPicker.addEventListener("change", () => {
  if (dayPicker.querySelector("input:checked")) {
    dayPicker.querySelector(".errorlist")?.remove();
    dayPicker.querySelectorAll("[aria-invalid]").forEach(input => input.removeAttribute("aria-invalid"));
  }
});
