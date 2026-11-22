const gardenCelebrations = [
  {name: "popper", icon: "🎉", praise: "Correct!", colors: ["#f2b540", "#e47662", "#70ba8e", "#92aedf", "#c393c8"]},
  {name: "bloom", icon: "🌼", praise: "You got it!", colors: ["#f397a9", "#edb852", "#b98bcd"]},
  {name: "stars", icon: "🌟", praise: "Nice work!", colors: ["#eaa62d", "#f6cf62", "#94b8e7"]},
  {name: "butterfly", icon: "🦋", praise: "That’s it!", colors: ["#73ae76", "#75bfc2", "#c4ab69"]}
];

function gardenAnswerNote(result, seed = 0) {
  const success = result !== "retry";
  const style = gardenCelebrations[seed % gardenCelebrations.length] || gardenCelebrations[0];
  const note = document.createElement("div");
  note.className = success ? "answer-party" : "retry-note";
  note.dataset.result = result;
  if (success) note.dataset.variant = style.name;
  const icon = document.createElement("span");
  icon.setAttribute("aria-hidden", "true");
  icon.className = "answer-icon";
  icon.textContent = success ? style.icon : "🌱";
  const label = document.createElement("strong");
  label.textContent = success ? (result === "correct" ? style.praise : "Well done!") : "Try again";
  note.append(icon, label);
  if (success && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const count = style.name === "popper" ? 24 : 12;
    for (let i = 0; i < count; i++) {
      const scrap = document.createElement("i");
      const angle = Math.PI * (1.03 + .94 * i / (count - 1));
      const reach = 56 + (i * 23) % 71;
      scrap.style.setProperty("--flight-x", "calc(" + Math.round(Math.cos(angle) * reach) + " * var(--burst-x, 1px))");
      scrap.style.setProperty("--flight-y", "calc(" + Math.round(Math.sin(angle) * reach - 15) + " * var(--burst-y, 1px))");
      scrap.style.setProperty("--spin", (i % 2 ? 1 : -1) * (110 + 13 * i) + "deg");
      scrap.style.setProperty("--delay", (i % 4) * 50 + "ms");
      scrap.style.backgroundColor = style.colors[i % style.colors.length];
      icon.append(scrap);
    }
  }
  return note;
}
