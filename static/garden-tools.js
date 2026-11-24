// The same drawing code updates a child's board and its read-only parent mirror.
function paintGardenTool(board, encoded = "") {
  const steps = /^(\d{1,2},){0,39}\d{1,2}$/.test(encoded) ? encoded.split(",").map(Number) : [];
  if (board.dataset.tool === "dots") return paintDots(board, steps);
  if (board.dataset.tool === "sort") return paintSort(board, steps);
  if (board.dataset.tool === "memory") return paintMemory(board, steps);
  if (board.dataset.tool === "balance") return paintBalance(board, steps);
  const count = steps.length;
  const check = board.querySelector("[data-check]");
  const undo = board.querySelector('[data-action="undo"]');
  if (undo) undo.disabled = !count;
  let value = "";
  switch (board.dataset.tool) {
    case "paint-mix":
      value = paintMixture(board, steps);
      break;
    case "shift": {
      const active = steps[0] === 1;
      const shift = board.querySelector('[data-action="shift"]');
      shift.setAttribute("aria-pressed", String(active));
      board.querySelectorAll("[data-letter]").forEach(key => {
        key.textContent = active ? key.dataset.letter.toUpperCase() : key.dataset.letter;
      });
      const initial = steps[1];
      board.querySelector("[data-initial]").textContent = initial >= 1 && initial <= 52
        ? String.fromCharCode(initial <= 26 ? initial + 64 : initial + 70) : "_";
      break;
    }
    case "backspace": {
      const sign = board.querySelector("[data-label]");
      value = sign.dataset.label.slice(0, Math.max(0, sign.dataset.label.length - count));
      sign.querySelector("output").textContent = value;
      board.querySelector('[data-action="erase"]').disabled = !value;
      break;
    }
    case "maze": {
      const maze = board.querySelector("[data-maze]");
      const layout = maze.dataset.maze;
      const where = steps[0] ?? layout.indexOf("B");
      Array.from(maze.children).forEach((cell, i) => {
        cell.textContent = i === where ? maze.dataset.player : layout[i] === "L" ? maze.dataset.goal : "";
      });
      break;
    }
    case "magic":
      board.querySelector("[data-e]").textContent = count ? "e" : "";
      board.querySelector(".picture-choices").hidden = !count;
      board.querySelector('[data-action="add-e"]').disabled = Boolean(count);
      break;
    case "drum":
      board.querySelector(".drum-pad").disabled = count >= 40;
      board.querySelector("[data-count]").textContent = count;
      value = String(count);
      break;
    case "sentence": {
      const tiles = [...board.querySelectorAll("[data-tile]")];
      value = steps.map(i => tiles[i]?.dataset.tile || "").join(" ");
      board.querySelector("output").textContent = value;
      tiles.forEach((tile, i) => { tile.disabled = steps.includes(i); });
      if (count !== tiles.length) value = "";
      break;
    }
    case "pairs":
      board.querySelectorAll("[data-pair]").forEach((pair, i) => {
        pair.setAttribute("aria-pressed", String(steps.includes(i)));
      });
      board.querySelector("[data-count]").textContent = count;
      break;
    case "measure":
      board.querySelectorAll(".acorn-ruler span").forEach((unit, i) => {
        const icon = board.querySelector("[data-unit]").dataset.unit;
        unit.classList.toggle("acorn", !icon && i < count);
        unit.textContent = icon && i < count ? icon : "";
      });
      board.querySelector('[data-action="count"]').disabled = count >= 6;
      value = String(count);
      break;
    case "coins":
      value = String(steps.reduce((sum, coin) => sum + coin, 0));
      board.querySelector("output").textContent = steps.map(coin => coin + "¢").join(" + ");
      break;
  }
  if (check) {
    check.value = value;
    check.disabled = !count || !value;
  }
}

function startGardenTool(board, form, answer, signal) {
  let steps = [];
  const tool = board.dataset.tool;
  function update() {
    form.elements.tool_state.value = steps.join(",");
    paintGardenTool(board, form.elements.tool_state.value);
  }
  if (tool === "dots") {
    board.addEventListener("click", event => {
      const dot = event.target.closest("[data-dot]");
      if (!dot || form.inert) return;
      const index = Number(dot.dataset.dot);
      if (index < steps.length) return;
      if (index !== steps.length) { answer("retry"); return; }
      steps.push(index);
      update();
    });
    update();
    return;
  }
  if (tool === "sort") {
    steps = Array(board.querySelectorAll("[data-piece]").length).fill(0);
    let selected = null;
    board.addEventListener("click", event => {
      const piece = event.target.closest("[data-piece]");
      const bin = event.target.closest("[data-bin]");
      if (piece) {
        selected = Number(piece.dataset.piece);
        board.querySelectorAll("[data-piece]").forEach(p => p.setAttribute("aria-pressed", String(p === piece)));
        board.querySelector("[data-sort-status]").textContent = piece.textContent.trim() + " selected. Choose a basket.";
      } else if (bin && selected !== null) {
        steps[selected] = Number(bin.dataset.bin);
        board.querySelector('[aria-pressed="true"]').setAttribute("aria-pressed", "false");
        selected = null;
        update();
      }
    });
    update();
    return;
  }
  if (tool === "balance" || tool === "memory") {
    startTableGame(board, steps, update, signal);
    update();
    return;
  }
  function typeInitial(letter) {
    const upper = letter === letter.toUpperCase();
    steps = [0, letter.toUpperCase().charCodeAt(0) - 64 + (upper ? 0 : 26)];
    update();
    answer(letter);
  }
  const moveBy = {"↑": -5, "↓": 5, "←": -1, "→": 1};
  function move(direction) {
    const maze = board.querySelector("[data-maze]").dataset.maze;
    const here = steps[0] ?? maze.indexOf("B");
    const next = here + moveBy[direction];
    if (next < 0 || next >= maze.length || Math.abs(next % 5 - here % 5) > 1 || maze[next] === "#") return;
    steps = [next];
    update();
    if (maze[next] === "L") answer(String(next));
  }
  board.addEventListener("click", event => {
    const button = event.target.closest('button[type="button"]');
    if (!button || form.inert) return;
    if (button.hasAttribute("data-pigment")) {
      if (steps.length === 2) steps = [];
      steps.push([...board.querySelectorAll("[data-pigment]")].indexOf(button));
    }
    if (button.dataset.direction) { move(button.dataset.direction); return; }
    if (button.dataset.letter) {
      typeInitial(steps[0] === 1 ? button.dataset.letter.toUpperCase() : button.dataset.letter);
      return;
    }
    if (button.hasAttribute("data-tile")) steps.push([...board.querySelectorAll("[data-tile]")].indexOf(button));
    if (button.hasAttribute("data-pair")) {
      const i = [...board.querySelectorAll("[data-pair]")].indexOf(button);
      steps = steps.includes(i) ? steps.filter(index => index !== i) : [...steps, i];
    }
    if (button.dataset.coin && steps.length < 40) steps.push(Number(button.dataset.coin));
    switch (button.dataset.action) {
      case "shift": steps = [steps[0] === 1 ? 0 : 1]; break;
      case "beat": {
        if (steps.length >= 40) break;
        steps.push(1);
        const drum = board.querySelector("[data-drum-sound]");
        drum.currentTime = 0;
        drum.play().catch(() => {}); // Counting also works with audio unavailable.
        break;
      }
      case "erase": case "count": if (steps.length < 40) steps.push(1); break;
      case "add-e": steps = [1]; break;
      case "undo": steps.pop(); break;
      case "reset": steps = []; break;
    }
    update();
  });
  if (["shift", "maze", "backspace"].includes(tool)) {
    document.addEventListener("keydown", event => {
      if (form.inert || event.ctrlKey || event.metaKey || event.altKey ||
          event.target.closest("a,button,input,textarea,select,summary") && !board.contains(event.target)) return;
      if (tool === "shift" && event.key === "Shift" && !event.repeat) { steps = [1]; update(); }
      const arrows = {ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→"};
      if (tool === "maze" && arrows[event.key]) { event.preventDefault(); move(arrows[event.key]); }
      if (tool === "backspace" && event.key === "Backspace") {
        event.preventDefault();
        if (!event.repeat) board.querySelector('[data-action="erase"]').click();
      }
      if (tool === "shift" && !event.repeat && /^[a-z]$/i.test(event.key)) {
        event.preventDefault();
        typeInitial(event.shiftKey ? event.key : event.key.toLowerCase());
      }
    }, {signal});
    if (tool === "shift") {
      document.addEventListener("keyup", event => {
        if (event.key === "Shift" && steps[0] === 1) { steps = [0]; update(); }
      }, {signal});
    }
  }
  update();
}

function memoryState(cards, steps) {
  let matched = 0;
  while (matched + 1 < steps.length && cards[steps[matched]].dataset.card === cards[steps[matched + 1]].dataset.card) matched += 2;
  return {matched, miss: steps.length === matched + 2};
}

function paintMemory(board, raw) {
  const cards = [...board.querySelectorAll("[data-card]")];
  const steps = [...new Set(raw.filter(i => i < cards.length))];
  const {matched, miss} = memoryState(cards, steps);
  const clues = board.querySelector("[data-clues]")?.checked;
  cards.forEach((card, i) => {
    const pos = steps.indexOf(i), up = pos >= 0, found = up && pos < matched;
    card.dataset.face = found ? "matched" : up ? "up" : "down";
    const face = card.querySelector(".card-face");
    face.hidden = !up;
    card.querySelector(".card-back").hidden = up;
    if (card.dataset.clip) face.textContent = clues ? card.dataset.label : "♫";
    const front = card.dataset.clip && !clues ? "sound card" : card.dataset.label;
    card.setAttribute("aria-label", "Card " + (i + 1) + ", " + (up ? front : "face down") + (found ? ", matched" : ""));
  });
  const status = matched / 2 + " of " + cards.length / 2 + " pairs found.";
  board.querySelector("[data-table-status]").textContent = status + (miss ? " Try another pair." : "");
  const finish = board.querySelector("[data-finish]");
  if (finish) {
    finish.disabled = matched !== cards.length;
    board.querySelector("[data-cover]").hidden = !miss;
  }
}

function paintBalance(board, raw) {
  const weights = [...board.querySelectorAll("[data-weight]")];
  const picks = [...new Set(raw.filter(i => i < weights.length))];
  const total = picks.reduce((sum, i) => sum + Number(weights[i].dataset.weight), 0);
  const scale = board.querySelector(".seesaw"), target = Number(scale.dataset.target);
  scale.style.setProperty("--tilt", Math.max(-13, Math.min(13, (total - target) * 4)) + "deg");
  weights.forEach((w, i) => w.setAttribute("aria-pressed", String(picks.includes(i))));
  const load = scale.querySelector("output");
  load.replaceChildren(...picks.map(i => {
    const block = document.createElement("b");
    block.textContent = weights[i].textContent.trim();
    return block;
  }));
  if (!picks.length) load.textContent = "0";
  board.querySelector("[data-table-status]").textContent = "Left " + target + " · Right " + total + ". " +
    (total === target ? "Balanced!" : total < target ? "The left side is heavier." : "The right side is heavier.");
  const check = board.querySelector("[data-weigh]");
  if (check) check.disabled = !picks.length;
}

function startTableGame(board, steps, update, signal) {
  const weights = [...board.querySelectorAll("[data-weight]")];
  weights.forEach((w, index) => w.onclick = () => {
    const old = steps.indexOf(index);
    if (old === -1) steps.push(index);
    else steps.splice(old, 1);
    update();
  });
  if (weights.length) return;
  const cards = [...board.querySelectorAll("[data-card]")];
  const audio = board.querySelector("[data-card-audio]");
  const repeat = board.querySelector("[data-repeat]");
  let last = null, playId = 0;
  function stop() { playId++; audio?.pause(); }
  function listen(card) {
    if (!audio || !card) return;
    stop();
    const id = playId;
    last = card; repeat.disabled = false;
    audio.src = card.dataset.clip;
    board.querySelector("[data-audio-error]").textContent = "";
    audio.play().catch(() => {
      if (id === playId && !signal.aborted) board.querySelector("[data-audio-error]").textContent = "Try Hear again, or turn on sound clues.";
    });
  }
  let coverTimer;
  function cover() {
    clearTimeout(coverTimer);
    if (!memoryState(cards, steps).miss) return;
    steps.splice(-2);
    // A spoken clue may outlast the reveal. Let it finish under the covered card.
    last = null;
    if (repeat) repeat.disabled = true;
    update();
  }
  cards.forEach((card, index) => card.onclick = () => {
    const {miss} = memoryState(cards, steps);
    if (steps.includes(index)) { listen(card); return; }
    if (miss) cover();
    steps.push(index);
    listen(card);
    update();
    if (memoryState(cards, steps).miss) coverTimer = setTimeout(cover, 1200);
  });
  signal.addEventListener("abort", () => clearTimeout(coverTimer), {once:true});
  board.querySelector("[data-cover]").onclick = cover;
  if (audio) {
    repeat.onclick = () => listen(last);
    board.querySelector("[data-clues]").onchange = update;
    document.querySelector("#listen")?.addEventListener("click", stop, {signal});
    audio.addEventListener("play", () => document.querySelector("#directions-audio")?.pause(), {signal});
    signal.addEventListener("abort", stop, {once:true});
    window.addEventListener("pagehide", stop, {signal});
  }
}

function paintMixture(board, steps) {
  const pots = [...board.querySelectorAll("[data-pigment]")];
  const chosen = steps.slice(0, 2).map(i => pots[i]).filter(Boolean);
  const names = chosen.map(pot => pot.dataset.pigment);
  const recipes = board.paintRecipes ??= JSON.parse(board.querySelector('script[type="application/json"]').textContent);
  const mix = recipes.find(r => names.includes(r.first) && names.includes(r.second));
  const name = mix?.result.name || names[0] || "";
  const color = mix?.result.color || chosen[0]?.style.getPropertyValue("--pigment") || "transparent";
  const sample = board.querySelector("[data-mixture]");
  sample.style.setProperty("--pigment", color);
  sample.querySelector(".paint-dab").classList.toggle("empty", !chosen.length);
  sample.querySelector("output").textContent = name || "Your mix";
  board.querySelector("[data-paint-recipe]").textContent = chosen.length === 2
    ? names.join(" + ") + " makes " + name + "."
    : chosen.length ? names[0] + " + … Choose another paint." : "Choose your first paint.";
  return chosen.length === 2 ? name : "";
}

function paintDots(board, steps) {
  const dots = [...board.querySelectorAll("[data-dot]")];
  const points = dots.slice(0, steps.length).map(dot => dot.dataset.x + "," + dot.dataset.y);
  const done = steps.length === dots.length;
  if (done) points.push(points[0]);
  board.querySelector("[data-dot-line]").setAttribute("points", points.join(" "));
  dots.forEach((dot, i) => dot.setAttribute("aria-pressed", String(i < steps.length)));
  const status = board.querySelector("[data-dot-status]");
  status.textContent = done ? "You drew a " + status.dataset.outline + "!" : steps.length + " of " + dots.length + " dots joined.";
  const finish = board.querySelector("[data-dot-finish]");
  if (finish) finish.disabled = !done;
}

function paintSort(board, steps) {
  const pieces = [...board.querySelectorAll("[data-piece]")];
  const areas = board.querySelectorAll("[data-area]");
  let count = 0;
  for (const piece of pieces) {
    const area = areas[steps[Number(piece.dataset.piece)]] || areas[0];
    if (piece.parentElement !== area) area.append(piece);
    if (area !== areas[0]) count++;
  }
  const check = board.querySelector("[data-sort-check]");
  if (check) check.disabled = count < pieces.length;
  board.querySelector("[data-sort-status]").textContent = count === pieces.length
    ? "All items placed. Check your baskets, or move an item." : "Choose an item, then a basket.";
}
