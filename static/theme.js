(() => {
  const key = "little-garden-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const choices = ["system", "light", "dark"];
  let mode = "system";
  try { mode = localStorage.getItem(key) || "system"; } catch {}
  function apply(choice) {
    mode = choices.includes(choice) ? choice : "system";
    document.documentElement.dataset.theme = mode === "system" ? (system.matches ? "dark" : "light") : mode;
    const selector = document.querySelector("#theme");
    if (selector) selector.value = mode;
  }
  apply(mode);
  system.addEventListener("change", () => apply(mode));
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) apply(event.newValue);
  });
  document.addEventListener("DOMContentLoaded", () => {
    const selector = document.querySelector("#theme");
    selector.value = mode;
    selector.addEventListener("change", () => {
      apply(selector.value);
      try { localStorage.setItem(key, mode); } catch {}
    });
  });
})();
