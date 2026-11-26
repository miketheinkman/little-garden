function paintAmountHint(root, count, coins = false) {
  const hint = root.querySelector("[data-amount-hint]");
  if (!hint) return;
  const left = Number(hint.dataset.target) - count;
  const cue = left === 0 ? "✓ Just right!" : left > 0 ? "↑ Add more." : "↓ Take some out.";
  hint.querySelector("[data-hint-message]").textContent = coins
    ? count + "¢ on the counter. " + (left > 0 ? left + "¢ to go." : left < 0 ? "Take back " + (-left) + "¢." : cue)
    : cue;
}

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
      const total = steps.reduce((sum, coin) => sum + coin, 0);
      value = String(total);
      paintAmountHint(board, total, true);
      board.querySelector("output").textContent = steps.map(coin => coin + "¢").join(" + ");
      break;
  }
  if (check) {
    check.value = value;
    check.disabled = board.dataset.tool !== "sentence" && (!count || !value);
  }
}

function startGardenTool(board, form, answer, signal, sounds) {
  let steps = [];
  const tool = board.dataset.tool;
  function update() {
    form.elements.tool_state.value = steps.join(",");
    paintGardenTool(board, form.elements.tool_state.value);
  }
  if (tool === "sentence") {
    const check = board.querySelector("[data-check]");
    const feedback = document.querySelector("#answer-feedback");
    check.after(feedback);
    form.addEventListener("submit", event => {
      if (check.value) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const remaining = board.querySelectorAll("[data-tile]:enabled").length;
      feedback.textContent = "Choose " + remaining + (remaining === 1 ? " more word." : " more words.");
    });
    board.addEventListener("click", event => {
      if (event.target.closest("[data-tile],[data-action]")) feedback.replaceChildren();
    });
  }
  if (tool === "dots") {
    const surface = board.querySelector(".dot-board");
    const dots = [...surface.querySelectorAll("[data-dot]")];
    const pencil = surface.querySelector("[data-dot-pencil]");
    let pointer = null;
    function join(index) {
      if (index < steps.length) return;
      if (index !== steps.length) { answer("retry"); return; }
      steps.push(index);
      update();
    }
    function lift() {
      pointer = null;
      pencil.setAttribute("visibility", "hidden");
    }
    lift();
    surface.addEventListener("click", event => {
      const dot = event.target.closest("[data-dot]");
      if (dot && !form.inert) join(Number(dot.dataset.dot));
    });
    surface.addEventListener("pointerdown", event => {
      const dot = event.target.closest("[data-dot]");
      if (!dot || pointer !== null || form.inert || event.button !== 0) return;
      const index = Number(dot.dataset.dot);
      if (index !== steps.length && index !== steps.length - 1) return;
      if (index === steps.length) join(index);
      pointer = event.pointerId;
      surface.setPointerCapture(pointer);
    });
    surface.addEventListener("pointermove", event => {
      if (pointer !== event.pointerId || !steps.length || form.inert) return;
      const next = dots[steps.length];
      if (!next) { lift(); return; }
      const target = next.getBoundingClientRect();
      if (event.clientX >= target.left && event.clientX <= target.right &&
          event.clientY >= target.top && event.clientY <= target.bottom) join(steps.length);
      const last = dots[steps.length - 1];
      const bounds = surface.getBoundingClientRect();
      pencil.setAttribute("x1", last.dataset.x);
      pencil.setAttribute("y1", last.dataset.y);
      pencil.setAttribute("x2", 100 * (event.clientX - bounds.left) / bounds.width);
      pencil.setAttribute("y2", 100 * (event.clientY - bounds.top) / bounds.height);
      pencil.setAttribute("visibility", steps.length === dots.length ? "hidden" : "visible");
    });
    surface.addEventListener("lostpointercapture", lift);
    surface.addEventListener("pointercancel", lift);
    surface.addEventListener("pointerup", lift);
    update();
    return;
  }
  if (tool === "sort") {
    steps = Array(board.querySelectorAll("[data-piece]").length).fill(0);
    let selected = null;
    let drag = null, suppressClick = false;
    function dropTarget(event) {
      return document.elementFromPoint(event.clientX, event.clientY)?.closest('.sort-bin,[data-area="0"]');
    }
    board.addEventListener("pointerdown", event => {
      const piece = event.target.closest("[data-piece]");
      suppressClick = false;
      if (!piece || drag || form.inert || event.button !== 0) return;
      drag = {piece, id:event.pointerId, x:event.clientX, y:event.clientY, moving:false};
      piece.setPointerCapture(event.pointerId);
    });
    board.addEventListener("pointermove", event => {
      if (drag?.id !== event.pointerId) return;
      if (Math.hypot(event.clientX-drag.x, event.clientY-drag.y) < 6 && !drag.moving) return;
      drag.moving = true;
      drag.piece.classList.add("dragging");
      drag.piece.style.translate = (event.clientX - drag.x) + "px " + (event.clientY - drag.y) + "px";
      board.querySelector(".drop-target")?.classList.remove("drop-target");
      const target = dropTarget(event);
      if (target && board.contains(target)) target.classList.add("drop-target");
    });
    function finishDrag(event) {
      if (drag?.id !== event.pointerId) return;
      const {piece, moving} = drag;
      drag = null;
      const target = moving && event.type === "pointerup" && dropTarget(event);
      piece.style.removeProperty("translate");
      piece.classList.remove("dragging");
      board.querySelector(".drop-target")?.classList.remove("drop-target");
      if (!moving) return;
      suppressClick = true;
      if (!target || !board.contains(target)) return;
      steps[Number(piece.dataset.piece)] = Number(target.querySelector("[data-bin]")?.dataset.bin || 0);
      selected = null;
      board.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
      board.querySelector("[data-unplace]").disabled = true;
      update();
    }
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) board.addEventListener(name, finishDrag);
    board.addEventListener("click", event => {
      const piece = event.target.closest("[data-piece]");
      if (suppressClick && event.detail) { suppressClick = false; return; }
      const bin = event.target.closest("[data-bin]");
      const remove = board.querySelector("[data-unplace]");
      if (event.target.closest("[data-sort-reset]")) {
        steps.fill(0);
      } else if (event.target.closest("[data-unplace]") && selected !== null) {
        steps[selected] = 0;
      } else if (piece) {
        selected = Number(piece.dataset.piece);
        board.querySelectorAll("[data-piece]").forEach(p => p.setAttribute("aria-pressed", String(p === piece)));
        remove.disabled = steps[selected] === 0;
        board.querySelector("[data-sort-status]").textContent = piece.textContent.trim() +
          (remove.disabled ? " selected. Choose a basket." : " selected. Choose another basket or take it out.");
        return;
      } else if (bin && selected !== null) {
        steps[selected] = Number(bin.dataset.bin);
      } else return;
      board.querySelector('[data-piece][aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
      selected = null;
      remove.disabled = true;
      update();
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
    steps = [steps[0] || 0, letter.toUpperCase().charCodeAt(0) - 64 + (upper ? 0 : 26)];
    update();
    answer(letter);
  }
  if (tool === "shift") {
    const shift = board.querySelector('[data-action="shift"]');
    let held = null;
    let letterPress = null;
    board.addEventListener("pointerdown", event => {
      const key = event.target.closest("[data-letter]");
      if (!key || event.button !== 0 || form.inert) return;
      letterPress = {id:event.pointerId, key, upper:steps[0] === 1};
    });
    board.addEventListener("pointerup", event => {
      if (letterPress?.id !== event.pointerId) return;
      const {key, upper} = letterPress;
      letterPress = null;
      if (!form.inert && key.contains(document.elementFromPoint(event.clientX, event.clientY))) {
        typeInitial(upper ? key.dataset.letter.toUpperCase() : key.dataset.letter);
      }
    });
    board.addEventListener("pointercancel", event => {
      if (letterPress?.id === event.pointerId) letterPress = null;
    });
    shift.addEventListener("pointerdown", event => {
      if (held !== null || event.button !== 0 || form.inert) return;
      held = event.pointerId;
      shift.setPointerCapture(held);
      steps = [1, steps[1] || 0];
      update();
    });
    function release(event) {
      if (held !== event.pointerId) return;
      held = null;
      const letter = event.type === "pointerup" && document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-letter]");
      steps[0] = 0;
      if (letter && board.contains(letter) && !form.inert) typeInitial(letter.dataset.letter.toUpperCase());
      else update();
    }
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) shift.addEventListener(name, release);
    window.addEventListener("blur", () => {
      held = null;
      if (steps[0]) { steps[0] = 0; update(); }
    }, {signal});
  }
  const moveBy = {"↑": -5, "↓": 5, "←": -1, "→": 1};
  function move(direction) {
    sounds.prepare();
    const maze = board.querySelector("[data-maze]").dataset.maze;
    const here = steps[0] ?? maze.indexOf("B");
    const next = here + moveBy[direction];
    const status = board.querySelector("[data-maze-status]");
    if (next < 0 || next >= maze.length || Math.abs(next % 5 - here % 5) > 1 || maze[next] === "#") {
      const pad = board.querySelector(`[data-direction="${direction}"]`);
      sounds.play("blocked");
      status.textContent = direction + " Blocked. Try another arrow.";
      const cell = board.querySelector("[data-maze]").children[here];
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
        const offset = {"↑":"0,-5px", "↓":"0,5px", "←":"-5px,0", "→":"5px,0"}[direction];
        cell.animate([{transform:"none"}, {transform:"translate(" + offset + ")"}, {transform:"none"}], 240);
      }
      board.querySelector("[data-blocked]")?.removeAttribute("data-blocked");
      pad.setAttribute("data-blocked", "");
      return;
    }
    sounds.play("move");
    status.textContent = "";
    board.querySelector("[data-blocked]")?.removeAttribute("data-blocked");
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
      if (event.detail) return;
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
      case "shift": return;
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
          event.target.closest("textarea,select,input,[contenteditable=true]") ||
          (event.target.closest("a,button,summary") && !board.contains(event.target) &&
           !event.target.closest("#listen,#stop-audio"))) return;
      if (tool === "shift" && event.key === "Shift" && !event.repeat) { steps[0] = 1; update(); }
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
        if (event.key === "Shift" && steps[0] === 1) { steps[0] = 0; update(); }
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
  const status = board.querySelector("[data-dot-status]");
  const outline = status.dataset.outline;
  if (done) {
    points.push(points[0]);
    // From the flap tip, the path returns to the first corner, then seals the top edge.
    if (outline === "envelope") points.push(points[dots.length - 2]);
  }
  board.querySelector("[data-dot-line]").setAttribute("points", points.join(" "));
  dots.forEach((dot, i) => dot.setAttribute("aria-pressed", String(i < steps.length)));
  const article = /^[aeiou]/i.test(outline) ? "an" : "a";
  status.textContent = done ? `You drew ${article} ${outline}!` : steps.length + " of " + dots.length + " dots joined.";
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
  const reset = board.querySelector("[data-sort-reset]");
  if (reset) reset.disabled = count === 0;
  board.querySelector("[data-sort-status]").textContent = count === pieces.length
    ? "Check your baskets. To fix one, select the item and choose another basket." : "Drag an item to a basket, or tap the item and then its basket.";
}
