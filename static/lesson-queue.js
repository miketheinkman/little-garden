(() => {
  const library = document.querySelector("#available-lessons");
  const notice = document.querySelector("[data-queue-status]");
  let noticeTimer;

  function announce(message) {
    clearTimeout(noticeTimer);
    notice.textContent = message;
    noticeTimer = setTimeout(() => { notice.textContent = ""; }, 5500);
  }
  function updateLibrary(active, form) {
    const cards = [...library.querySelectorAll("[data-lesson]")];
    const index = cards.indexOf(form.closest("article"));
    const remaining = cards.filter(card => !active.has(card.dataset.lesson));
    const next = cards.slice(index + 1).find(card => !active.has(card.dataset.lesson)) || remaining.at(-1);
    const oldTop = cards[index]?.getBoundingClientRect().top;
    cards.forEach(card => { if (active.has(card.dataset.lesson)) card.remove(); });
    library.querySelectorAll("section").forEach(section => {
      if (!section.querySelector("article")) section.remove();
    });
    library.querySelector("[data-available]").textContent = remaining.length;
    const bulk = library.querySelector("[data-schedule-all]");
    const url = new URL(bulk.href);
    url.searchParams.set("batch", remaining.map(card => card.dataset.lesson).join(","));
    bulk.href = url;
    bulk.querySelector("span").textContent = remaining.length;
    library.querySelector(".bulk-queue").hidden = !remaining.length;
    const empty = library.querySelector("[data-empty]");
    empty.hidden = Boolean(remaining.length);
    if (next) {
      next.querySelector("button").focus({preventScroll: true});
      if (index >= 0) window.scrollBy(0, next.getBoundingClientRect().top - oldTop);
    } else {
      empty.focus({preventScroll: true});
    }
  }
  document.addEventListener("garden:scheduled", event => {
    const {active, opener, message} = event.detail;
    if (library && [...library.querySelectorAll("[data-lesson]")].some(card => active.includes(card.dataset.lesson))) {
      updateLibrary(new Set(active), opener);
    }
    if (notice) announce(message);
  });
  document.addEventListener("submit", async event => {
    const form = event.target;
    if (!form.matches("[data-queue-form],[data-dashboard-add]")) return;
    event.preventDefault();
    const button = form.querySelector("button");
    if (button.disabled) return;
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    button.disabled = true;
    try {
      if (form.matches("[data-dashboard-add]")) {
        const card = form.closest("[data-learner]");
        const response = await fetch(form.getAttribute("action"), {method: "POST", body: data, cache: "no-store"});
        if (!response.ok) throw new Error();
        const html = new DOMParser().parseFromString(await response.text(), "text/html");
        const updated = html.querySelector('[data-learner="' + card.dataset.learner + '"]');
        if (!updated) throw new Error();
        const anchor = card.querySelector("[data-placement-panel] > summary");
        const top = anchor.getBoundingClientRect().top;
        for (const selector of ["[data-current-queue]", "[data-suggested-lessons]", "[data-available-checkins]"]) {
          card.querySelector(selector).replaceWith(updated.querySelector(selector));
        }
        anchor.focus({preventScroll:true});
        window.scrollBy(0, anchor.getBoundingClientRect().top - top);
        announce("Lesson added to the queue.");
        return;
      }
      const response = await fetch(form.getAttribute("action") || location.href, {
        method: "POST", body: data, headers: {Accept: "application/json"}, cache: "no-store"
      });
      if (!response.ok || response.redirected) throw new Error();
      const result = await response.json();
      if (library) updateLibrary(new Set(result.active), form);
      else {
        const confirmation = document.createElement("span");
        confirmation.textContent = result.message;
        form.replaceWith(confirmation);
      }
      announce(result.message);
    } catch {
      announce("Couldn’t confirm the queue update. Please try again.");
    } finally {
      button.disabled = false;
    }
  });
  window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
})();
