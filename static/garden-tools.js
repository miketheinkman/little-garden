// The same drawing code updates a child's board and its read-only parent mirror.
function paintGardenTool(board, encoded = "") {
  const steps = /^(\d{1,2},){0,39}\d{1,2}$/.test(encoded) ? encoded.split(",").map(Number) : [];
  const count = steps.length;
  const check = board.querySelector("[data-check]");
  const undo = board.querySelector('[data-action="undo"]');
  if (undo) undo.disabled = !count;
  let value = "";
  switch (board.dataset.tool) {
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
