function gardenAnswerNote(result) {
  const success = result !== "retry";
  const note = document.createElement("div");
  note.className = success ? "answer-party" : "retry-note";
  const icon = document.createElement("span");
  icon.setAttribute("aria-hidden", "true");
  icon.className = "answer-icon";
  icon.textContent = success ? "🎉" : "🌱";
  const label = document.createElement("strong");
  label.textContent = success ? (result === "correct" ? "Correct!" : "Well done!") : "Try again";
  note.append(icon, label);
  if (success && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const colors = ["#f2b540", "#e47662", "#70ba8e", "#92aedf", "#c393c8"];
    for (let i = 0; i < 24; i++) {
      const scrap = document.createElement("i");
      const angle = Math.PI * (1.03 + .94 * i / 23);
      const reach = 56 + (i * 23) % 71;
      scrap.style.setProperty("--flight-x", Math.round(Math.cos(angle) * reach) + "px");
      scrap.style.setProperty("--flight-y", Math.round(Math.sin(angle) * reach - 15) + "px");
      scrap.style.setProperty("--spin", (i % 2 ? 1 : -1) * (110 + 13 * i) + "deg");
      scrap.style.setProperty("--delay", (i % 4) * 50 + "ms");
      scrap.style.backgroundColor = colors[i % colors.length];
      icon.append(scrap);
    }
  }
  return note;
}
