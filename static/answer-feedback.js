function startAnswerFeedback(activity) {
  const skip = document.querySelector(".skip-step");
  const feedback = document.querySelector("#answer-feedback");
  let busy = false;

  function lock(locked) {
    busy = locked;
    activity.inert = locked;
    skip.inert = locked;
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const focus = document.activeElement;
    const data = new FormData(event.currentTarget); // Also captures active keyboard time.
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    activity.querySelector("[data-generated-answer]")?.remove();
    document.querySelector("#native-retry")?.remove();
    feedback.replaceChildren();
    lock(true);
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(location.href, {
        method: "POST", signal: controller.signal, body: data, headers: {Accept: "application/json"}, cache: "no-store"
      });
      if (!response.ok) throw new Error();
      if (response.redirected) { location.replace(response.url); return; }
      const reply = await response.json();
      if (!activity.isConnected) return;
      if (reply.result === "retry") {
        lock(false);
        focus?.focus({preventScroll: true});
        if (focus?.matches('input[type="text"]')) focus.select();
        feedback.replaceChildren(gardenAnswerNote("retry"));
        document.dispatchEvent(new Event("garden-answer"));
        return;
      }
      if (!reply.next) throw new Error();
      if (reply.result === "correct" || reply.result === "finished") {
        feedback.replaceChildren(gardenAnswerNote(reply.result, Number(feedback.dataset.successSeed)));
        document.dispatchEvent(new Event("garden-answer"));
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      if (!activity.isConnected) return;
      if (document.querySelector("#live-presence")) await openLearnerPage(reply.next);
      else location.assign(reply.next);
    } catch {
      // A lost response can follow a successful save. Read the current step before resubmitting.
      feedback.textContent = "Let’s check where you left off. ";
      const link = document.createElement("a");
      link.href = location.href;
      link.textContent = "Reopen this step";
      feedback.append(link);
      link.focus();
    } finally {
      clearTimeout(deadline);
    }
  }
  activity.addEventListener("submit", submit);
  if (document.querySelector("#live-presence")) skip.addEventListener("submit", submit);
  window.addEventListener("pageshow", event => {
    if (event.persisted && busy) location.reload();
  }, {signal: lessonEvents.signal});
}

let lessonEvents;
function startLesson() {
  lessonEvents?.abort();
  const form = document.querySelector("#activity");
  if (!form) return;
  lessonEvents = new AbortController();
  startActivity(form, lessonEvents.signal);
  startAnswerFeedback(form);
}
startLesson();
