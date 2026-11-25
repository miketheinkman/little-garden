function positionQuestion() {
  const prompt = document.getElementById("prompt");
  const activity = document.getElementById("activity");
  if (!prompt || !activity) return;

  // Leave room around a short question. Give a tall board the full viewport below its directions.
  const start = document.querySelector("[data-parent-prep]") || prompt.closest(".question-heading");
  const top = start.getBoundingClientRect().top;
  const grid = activity.querySelector(".route-grid");
  if (grid) {
    const bounds = grid.getBoundingClientRect();
    const go = activity.querySelector("[data-run]").getBoundingClientRect();
    // Budget space for the actual prompt and Go button before sizing the board.
    const overhead = bounds.top - top + go.bottom - bounds.bottom + 32;
    grid.style.setProperty("--route-overhead", Math.ceil(overhead) + "px");
  }
  const height = activity.closest(".question-work-area").getBoundingClientRect().bottom - top;
  const inset = Math.max(16, (document.documentElement.clientHeight - height) / 2);
  prompt.focus({preventScroll: true});
  window.scrollBy({top: top - inset, behavior: "instant"});
}

window.addEventListener("pageshow", event => {
  if (event.persisted || location.hash || !document.getElementById("activity")) return;
  // Run after native scroll restoration and the lesson controls' initial layout.
  requestAnimationFrame(positionQuestion);
});
