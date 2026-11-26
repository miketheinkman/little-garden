function paintHarvest(board, shares) {
  const pens = [...board.querySelectorAll(".rabbit-pen")];
  const total = Number(board.dataset.carrots);
  const counts = shares ? shares.split(",").map(Number) : pens.map(() => 0);
  const used = counts.reduce((sum, count) => sum + count, 0);
  if (counts.length !== pens.length || used > total ||
      counts.some(count => !Number.isInteger(count) || count < 0)) return;
  board.querySelector("[data-left]").textContent = total - used;
  pens.forEach((pen, index) => {
    pen.querySelector("output").textContent = counts[index];
    pen.querySelector(".carrot-pile").textContent = board.dataset.icon.repeat(counts[index]);
    const feed = pen.querySelector("[data-feed]");
    if (feed) {
      feed.disabled = used === total;
      pen.querySelector("[data-take]").disabled = counts[index] === 0;
    }
  });
}

function startHarvest(board, form) {
  const buttons = [...board.querySelectorAll("[data-feed]")];
  const counts = buttons.map(() => 0);
  const total = Number(board.dataset.carrots);
  const finish = form.querySelector("[data-finish-sharing]");
  const reset = board.querySelector("[data-redeal]");
  function update() {
    const used = counts.reduce((sum, n) => sum + n, 0);
    const equal = used === total && counts.every(n => n === counts[0]);
    form.elements.shares.value = counts.join(",");
    paintHarvest(board, form.elements.shares.value);
    reset.hidden = !used;
    finish.disabled = used > 0 && !equal;
    finish.querySelector("[data-sharing-label]").textContent = used ? "We shared equally" : "We shared with our own counters";
    board.querySelector("[data-share-hint]").textContent = used === total
      ? (equal ? "Each " + board.dataset.role + " has " + counts[0] + " " + board.dataset.plural + "." : "Look at the piles. Take one back and give it to another helper.") : "";
  }
  buttons.forEach((button, index) => {
    const take = button.closest(".rabbit-pen").querySelector("[data-take]");
    take.hidden = false;
    take.onclick = () => { if (counts[index]) counts[index]--; update(); };
    button.hidden = false;
    button.onclick = () => { counts[index]++; update(); };
  });
  reset.onclick = () => { counts.fill(0); update(); };
  update();
}
