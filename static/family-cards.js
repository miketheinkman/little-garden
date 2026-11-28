(() => {
  const menus = [...document.querySelectorAll(".learner-menu")];
  function expand(button, open) {
    button.setAttribute("aria-expanded", String(open));
    document.getElementById(button.getAttribute("aria-controls")).hidden = !open;
  }
  for (const card of document.querySelectorAll(".family-card")) {
    const button = card.querySelector(".learner-toggle");
    button.addEventListener("click", () => expand(button, button.getAttribute("aria-expanded") !== "true"));
    const key = "garden-return-to-card";
    try {
      if (sessionStorage.getItem(key) === card.dataset.learner) {
        sessionStorage.removeItem(key);
        expand(button, true);
      }
    } catch {}
    card.addEventListener("submit", e => {
      if (e.target.matches("[data-dashboard-add]") || e.submitter?.value === "play") return;
      try { sessionStorage.setItem(key, card.dataset.learner); } catch {}
    });
  }
  document.addEventListener("click", e => {
    for (const menu of menus) if (!menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("focusin", e => {
    for (const menu of menus) if (!menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    const menu = menus.find(m => m.open);
    if (menu) {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  });
})();
