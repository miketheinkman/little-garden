document.querySelectorAll("[data-look-form]").forEach(form => {
  const preview = form.querySelector("[data-look-preview]");
  form.addEventListener("input", event => {
    const {font, accent, use_accent} = form.elements;
    if (event.target === accent) use_accent.checked = true;
    preview.dataset.font = font.value;
    preview.toggleAttribute("data-accent", use_accent.checked);
    const color = accent.value;
    const channels = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255)
      .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    const lum = channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    preview.style.setProperty("--learner-accent", color);
    if (use_accent.checked) preview.style.setProperty("--button-text", lum > .179 ? "#000" : "#fff");
    else preview.style.removeProperty("--button-text");
  });
});
