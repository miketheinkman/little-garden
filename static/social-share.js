(() => {
  const footer = document.getElementById("share-garden");
  if (!footer) return;
  for (const button of footer.querySelectorAll("[data-copy-link]")) {
    const panel = button.closest(".share-help");
    const field = panel.querySelector("input");
    const status = panel.querySelector('[role="status"]');
    button.hidden = false;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(field.value);
        status.textContent = "Link copied.";
      } catch {
        field.focus();
        field.select();
        status.textContent = "The link is selected. Use your device’s Copy command.";
      }
    });
  }
  const button = footer.querySelector("[data-share-device]");
  if (typeof navigator.share === "function") {
    button.hidden = false;
    button.addEventListener("click", async () => {
      try {
        await navigator.share({title: "Little Garden", url: button.dataset.url});
      } catch (error) {
        if (error.name !== "AbortError") {
          footer.querySelector("[data-share-status]").textContent = "Choose a sharing icon above.";
        }
      }
    });
  }
})();
