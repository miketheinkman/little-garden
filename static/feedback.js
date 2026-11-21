const feedbackForm = document.querySelector("#feedback form");
feedbackForm.addEventListener("submit", async event => {
  const button = event.submitter;
  if (!button || !window.fetch) return;
  event.preventDefault();
  const fields = new FormData(feedbackForm);
  fields.set("kind", button.value);
  const buttons = feedbackForm.querySelectorAll("button");
  const status = document.querySelector("#feedback-status");
  buttons.forEach(item => { item.disabled = true; });
  status.textContent = "Saving feedback…";
  try {
    const response = await fetch(window.location.href, {
      method: "POST", body: fields, headers: {Accept: "application/json"}
    });
    if (!response.ok || !(await response.json()).saved) throw new Error();
    feedbackForm.reset();
    status.textContent = "Saved · " + button.textContent;
  } catch {
    status.textContent = "Couldn’t confirm the save. Check your saved feedback before trying again.";
  } finally {
    buttons.forEach(item => { item.disabled = false; });
  }
});
