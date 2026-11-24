function positionQuestion() {
  const prompt = document.querySelector("#prompt");
  const activity = document.querySelector("#activity");
  if (!prompt || !activity) {
    window.scrollTo(0, 0);
    return;
  }
  const prep = document.querySelector("[data-parent-prep]");
  const start = prep || (document.querySelector("#live-presence") && document.querySelector("[data-question-start]"))
    || prompt.closest(".question-heading");
  const bottom = activity.getBoundingClientRect().bottom + window.scrollY;
  const top = start.getBoundingClientRect().top + window.scrollY;
  const landscapeTablet = matchMedia("(orientation: landscape) and (pointer: coarse) and (max-height: 900px)").matches;
  window.scrollTo({top: landscapeTablet || bottom > window.innerHeight ? Math.max(0, top - 16) : 0, behavior: "instant"});
}

window.addEventListener("pageshow", event => {
  if (event.persisted || !document.querySelector("#activity")) return;
  if (document.querySelector("#live-presence")) {
    positionQuestion();
    return;
  }
  // Parents can use the planning controls on entry. While testing a lesson on
  // a landscape tablet, land on the next question when they advance a step.
  if (!document.referrer || !matchMedia("(orientation: landscape) and (pointer: coarse)").matches) return;
  const previous = new URL(document.referrer);
  const path = location.pathname;
  if (previous.origin === location.origin && previous.pathname !== path &&
      previous.pathname.replace(/\d+\/$/, "") === path.replace(/\d+\/$/, "")) positionQuestion();
});
