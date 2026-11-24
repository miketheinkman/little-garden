(() => {
  function updateFields(form) {
    const repeat = form.elements.repeat.value;
    form.querySelector("[data-weekdays]").hidden = repeat !== "weekly";
    form.elements.end.disabled = repeat === "once";
    form.querySelector("[data-end]").hidden = repeat === "once";
    form.querySelector("[data-repeat-note]").hidden = repeat === "once";
  }

  document.querySelectorAll("[data-schedule-form]").forEach(updateFields);
  document.addEventListener("change", ({target}) => {
    const form = target.closest("[data-schedule-form]");
    if (!form) return;
    if (target.name === "repeat") updateFields(form);
    if (target.name === "weekdays" && target.checked) {
      const days = target.closest("fieldset");
      days.querySelector(".errorlist")?.remove();
      days.querySelectorAll("[aria-invalid]").forEach(input => input.removeAttribute("aria-invalid"));
    }
  });

  const dialog = document.querySelector(".schedule-dialog");
  if (!dialog || !dialog.showModal) return;
  const body = dialog.querySelector("[data-schedule-body]");
  const status = dialog.querySelector("[data-schedule-status]");
  const headers = {"X-Garden-Dialog": "schedule"};
  let opener, generation = 0;

  function showForm(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const form = doc.querySelector("[data-schedule-form]");
    if (!form) throw new Error();
    body.replaceChildren(form);
    updateFields(form);
    status.textContent = "";
    (form.querySelector("[aria-invalid=true]") || form.elements.start).focus();
  }

  const close = dialog.querySelector("[data-close]");
  dialog.addEventListener("cancel", event => { if (close.disabled) event.preventDefault(); });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { generation++; });
  document.addEventListener("click", async event => {
    const link = event.target.closest("a[data-schedule]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    opener = link;
    const current = ++generation;
    body.replaceChildren();
    status.textContent = "Loading schedule…";
    dialog.showModal();
    try {
      const response = await fetch(link.href, {headers, cache: "no-store"});
      if (!response.ok || response.redirected) throw new Error();
      const html = await response.text();
      if (current === generation && dialog.open) showForm(html);
    } catch {
      if (current !== generation || !dialog.open) return;
      const fallback = document.createElement("a");
      fallback.href = link.href;
      fallback.textContent = "Open the scheduling page";
      status.replaceChildren("Couldn’t load the schedule. ", fallback);
    }
  });

  dialog.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.target;
    const submit = form.querySelector("button");
    if (submit.disabled) return;
    submit.disabled = true;
    close.disabled = true;
    status.textContent = "Saving schedule…";
    const trigger = opener;
    const current = generation;
    try {
      const response = await fetch(form.action, {method: "POST", body: new FormData(form), headers});
      if (response.status === 422) {
        const html = await response.text();
        if (dialog.open && generation === current) showForm(html);
        return;
      }
      if (!response.ok || response.redirected) throw new Error();
      const result = await response.json();
      if (result.calendar) {
        location.assign(result.calendar);
        return;
      }
      if (generation === current && dialog.open) dialog.close();
      document.dispatchEvent(new CustomEvent("garden:scheduled", {detail: {...result, opener: trigger}}));
      if (document.querySelector(".review-lesson") ||
          (!document.querySelector("#available-lessons") && result.dueToday)) {
        location.reload();
      }
    } catch {
      if (current === generation) status.textContent = "Couldn’t confirm the schedule. Please try saving again.";
    } finally {
      submit.disabled = false;
      close.disabled = false;
    }
  });
})();
