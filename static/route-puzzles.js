// State values describe edits relative to the authored board. Go and completion use
// the same route simulation on the server, including for a parent preview.
const routeDirections = ["north", "east", "south", "west"];
const routeEdges = ["32 0", "64 32", "32 64", "0 32"];

function routePiece(cell, state) {
  let angle = cell.angle;
  let ports = [1, 3], label = "straight", cue = "";
  switch (cell.kind) {
    case "grass": return {ports: [], label: "ground", cue};
    case "source": ports = [0]; label = "start"; break;
    case "goal": return {ports: [], label: "destination", cue};
    case "tee": ports = [3, 1, 2]; label = "fork"; break;
    case "passenger": label = "passenger"; break;
    case "valve": case "openValve": {
      const open = Boolean(state) !== (cell.kind === "openValve");
      label = open ? "open valve" : "closed valve";
      cue = open ? "○" : "×";
      break;
    }
    case "switch": ports = [3, state ? 2 : 1]; label = "switch"; cue = "⇄"; break;
    case "socket":
      if (!state) return {ports: [], label: "empty space", cue: "+"};
      angle += state - 1;
      ports = [0, 1]; label = "bend"; cue = "↻"; break;
    case "turnBend": angle += state; cue = "↻"; // falls through
    case "bend": ports = [0, 1]; label = "bend"; break;
    case "turnLine": angle += state; cue = "↻"; break;
  }
  return {ports: ports.map(port => (port + angle) % 4), label, cue};
}

function routeDrawing(ports, train, inactive) {
  const path = ports.length === 2
    ? 'M' + routeEdges[ports[0]] + ' Q32 32 ' + routeEdges[ports[1]]
    : ports.map(port => 'M32 32 L' + routeEdges[port]).join(' ');
  const spare = inactive == null ? '' : '<path d="M32 32 L' + routeEdges[inactive] + '" stroke="var(--rail)" stroke-width="5" stroke-dasharray="3 4"/>';
  return '<svg viewBox="0 0 64 64" aria-hidden="true" fill="none">' + spare +
    '<path d="' + path + '" stroke="var(--rail)" stroke-width="' + (train ? 15 : 19) + '"/>' +
    '<path class="route-core" d="' + path + '" stroke="var(--track)" stroke-width="' + (train ? 9 : 12) + '"/>' +
    (train ? '<path d="' + path + '" stroke="var(--rail)" stroke-width="12" stroke-dasharray="2 7"/>' : '') + '</svg>';
}

function routeRenderer(root) {
  const board = JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  const grid = root.querySelector(".route-grid");
  grid.style.setProperty("--cols", board.width);
  grid.style.setProperty("--rows", board.cells.length / board.width);
  const train = board.mode === "train", mirror = root.hasAttribute("data-mirror");
  const nodes = board.cells.map((cell, index) => {
    const node = document.createElement(cell.states > 1 && !mirror ? "button" : "span");
    if (node.tagName === "BUTTON") node.type = "button";
    node.className = cell.states > 1 ? "route-cell route-editable" : "route-cell";
    node.dataset.index = index;
    grid.append(node);
    return node;
  });
  const token = document.createElement("span");
  token.className = "route-token";
  token.setAttribute("aria-hidden", "true");
  token.textContent = train ? "🚂" : "💧";
  grid.append(token);
  const mutable = board.cells.flatMap((cell, i) => cell.states > 1 ? [i] : []);
  const source = board.cells.findIndex(cell => cell.kind === "source");

  function paint(moves, trace = [], spot = -1, hint = -1) {
    if (workshopMessages[board.mode]) {
      paintWorkshop(root, board, nodes, mutable, token, moves, trace, spot, hint);
      return;
    }
    board.cells.forEach((cell, index) => {
      const node = nodes[index], state = moves[mutable.indexOf(index)] || 0;
      if (node.dataset.state !== String(state)) {
        node.dataset.state = state;
        const {ports, label, cue} = routePiece(cell, state);
        const inactive = cell.kind === "switch" ? (cell.angle + (state ? 1 : 2)) % 4 : null;
        // Destinations have a short approach from each adjacent track or pipe.
        if (cell.kind === "goal") {
          const x = index % board.width, y = Math.floor(index / board.width);
          [[0,-1], [1,0], [0,1], [-1,0]].forEach(([dx, dy], direction) => {
            const col = x + dx, row = y + dy;
            const neighbor = board.cells[row * board.width + col];
            if (col >= 0 && col < board.width && neighbor && neighbor.kind !== "grass") ports.push(direction);
          });
        }
        node.innerHTML = routeDrawing(ports, train, inactive);
        let figure = "", name = label;
        if (cell.kind === "goal") {
          figure = root.dataset.landmark;
          name = root.dataset.place + " destination";
          const flag = document.createElement("span");
          flag.className = "route-flag"; flag.textContent = "⚑"; node.append(flag);
        }
        if (cell.kind === "source") figure = train ? "🚉" : "🚰";
        if (cell.kind === "grass" && index % 3 === 0) figure = root.dataset.scenery;
        if (cell.kind === "passenger") {figure = root.dataset.friend; name = root.dataset.friendName + " passenger";}
        if (["valve", "openValve"].includes(cell.kind)) {
          node.classList.add("route-valve");
          node.classList.toggle("route-valve-open", label === "open valve");
          const wheel = document.createElement("span");
          wheel.className = "route-figure";
          wheel.innerHTML = '<svg viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3"><circle cx="16" cy="16" r="11"/><path d="M16 5v22M5 16h22"/><circle cx="16" cy="16" r="3" fill="currentColor"/></svg>';
          node.append(wheel);
        }
        if (figure) {
          const icon = document.createElement("span");
          icon.className = "route-figure" + (cell.kind === "grass" ? " route-scenery" : "");
          icon.textContent = figure; icon.setAttribute("aria-hidden", "true"); node.append(icon);
        }
        if (cue) {
          const mark = document.createElement("span");
          mark.className = "route-mark"; mark.textContent = cue; node.append(mark);
        }
        const directions = ports.map(port => routeDirections[port]).join(" and ");
        const description = name + (directions ? ", " + directions : "") +
          ", row " + (Math.floor(index / board.width) + 1) + ", column " + (index % board.width + 1);
        node.setAttribute("aria-label", description);
        if (node.tagName !== "BUTTON") node.setAttribute("role", "img");
      }
      node.classList.toggle("is-wet", !train && trace.includes(index));
      node.classList.toggle("is-picked-up", cell.kind === "passenger" && trace.includes(index));
      node.classList.toggle("is-arrived", cell.kind === "goal" && trace.includes(index));
      node.classList.toggle("is-stop", index === spot);
      node.classList.toggle("is-hint", index === hint);
      if (index === spot || index === hint) node.dataset.marker = index === spot ? "!" : "☀";
      else delete node.dataset.marker;
    });
    const passenger = trace.some(i => board.cells[i].kind === "passenger");
    if (train) token.dataset.rider = passenger ? root.dataset.friend : "";
    const at = trace.length ? trace[trace.length - 1] : source;
    token.style.transform = 'translate(' + (at % board.width * 100) + '%, ' + (Math.floor(at / board.width) * 100) + '%)';
  }
  return {board, mutable, paint, nodes};
}

function paintRouteMirror(root, encoded) {
  const view = root.routeView || (root.routeView = routeRenderer(root));
  const values = /^(?:\d{1,2},){0,39}\d{1,2}$/.test(encoded) ? encoded.split(",").map(Number) : [];
  const n = view.mutable.length;
  view.paint(values.slice(0, n), values.slice(n + 2).filter(i => i < view.board.cells.length),
             (values[n] || 0) - 1, (values[n + 1] || 0) - 1);
}

function startRoutePuzzle(root, form, signal) {
  const {board, mutable, paint, nodes} = routeRenderer(root);
  const button = key => root.querySelector("[data-" + key + "]");
  const message = root.querySelector(".route-message");
  const initial = mutable.map(() => 0);
  let moves = initial.slice(), history = [], trace = [], spot = -1, highlight = -1;
  let busy = "", solved = false, selected = false, version = 0, hintDepth = 0;
  let help = Number(root.dataset.help);
  const spare = button("spare"), socket = board.cells.findIndex(cell => cell.kind === "socket");
  function refresh() {
    paint(moves, trace, spot, highlight);
    root.classList.toggle("route-solved", solved);
    form.elements.moves.value = moves.join("");
    form.elements.tool_state.value = [...moves, spot + 1, highlight + 1, ...trace].join(",");
    for (const i of mutable) nodes[i].disabled = Boolean(busy);
    spare.hidden = socket < 0 || moves[mutable.indexOf(socket)] > 0;
    spare.disabled = busy;
    spare.setAttribute("aria-pressed", String(selected));
    button("run").hidden = busy || solved;
    button("stop").hidden = busy !== "run";
    button("next").hidden = !solved;
    button("undo").disabled = busy || !history.length;
    button("reset").disabled = busy || (!history.length && !trace.length && highlight < 0 && !selected);
    button("hint").disabled = busy || solved;
    button("parent").disabled = busy || Boolean(help & 2);
    if (help & 2) button("parent").textContent = "✓ Grown-up help recorded";
  }
  function clearRun() {
    solved = false; trace = []; spot = highlight = -1; selected = false; hintDepth = 0;
  }
  function edit(index) {
    if (busy) return;
    const position = mutable.indexOf(index), cell = board.cells[index];
    if (position < 0) return;
    if (cell.kind === "socket" && !moves[position] && !selected) {
      message.textContent = "Pick the spare bend, then tap this space.";
      spare.focus(); return;
    }
    history.push(moves.slice());
    moves[position] = (moves[position] + 1) % cell.states;
    if (cell.kind === "socket" && !moves[position]) moves[position] = 1;
    clearRun(); refresh();
    message.textContent = nodes[index].getAttribute("aria-label") + ".";
  }
  for (const index of mutable) nodes[index].onclick = () => edit(index);
  spare.onclick = () => {
    selected = !selected; refresh();
    message.textContent = selected ? "Now tap the empty square." : "Pick a piece when you’re ready.";
    if (selected) nodes[socket].focus();
  };
  if (socket >= 0) {
    spare.ondragstart = event => { selected = true; event.dataTransfer.setData("text/plain", "bend"); refresh(); };
    nodes[socket].ondragover = event => event.preventDefault();
    nodes[socket].ondrop = event => { event.preventDefault(); if (selected) edit(socket); };
    spare.ondragend = () => { selected = false; refresh(); };
  }
  button("undo").onclick = () => {
    moves = history.pop(); clearRun(); refresh(); message.textContent = "One move back.";
  };
  button("reset").onclick = () => {
    history = []; moves = initial.slice(); clearRun(); refresh(); message.textContent = "Ready for a fresh start.";
  };
  button("stop").onclick = () => {
    version++; busy = ""; refresh(); message.textContent = "Paused. Change a piece or press Go to start again.";
    button("run").focus();
  };
  async function request(action) {
    const id = ++version;
    busy = action; refresh();
    const data = new FormData(form);
    data.set("action", action);
    try {
      const reply = await fetch(location.href, {method:"POST", body:data, signal, headers:{Accept:"application/json"}});
      if (!reply.ok || reply.redirected) throw new Error();
      const result = await reply.json();
      if (signal.aborted || id !== version || !root.isConnected) return;
      if (action === "run") {
        trace = []; spot = highlight = -1;
        message.textContent = workshopMessages[board.mode]?.[0] || (board.mode === "water" ? "Here comes the water…" : "All aboard!");
        for (const at of result.trace) {
          if (id !== version || signal.aborted || !root.isConnected) return;
          trace.push(at); refresh();
          await new Promise(resolve => setTimeout(resolve, 330));
        }
        if (id !== version || signal.aborted || !root.isConnected) return;
        solved = result.success;
        spot = solved ? -1 : result.spot;
        const reasons = {edge:"The path ran off the board.", rock:"A rock blocks this path.", pickup:"A stop was missed.",
          spin:"The flower is turning the other way.", gears:"The gears stop turning here.", bridge:"There is still a gap at the bank.",
          gates:"The marked gate is locked.", closed: "The water stopped at this closed wheel.", gap: "The path stops at the marked square.", goal: "Can you reach the marked flag?",
          passenger: "The passenger is still waiting at the marked square.", loop: "The route came back to the same place."};
        message.textContent = solved ? workshopMessages[board.mode]?.[1] || (board.mode === "water" ? "Splash! Every flag got water." : "Pulling in. You reached the station!") : reasons[result.reason] + " Try a change.";
      } else if (action === "hint") {
        help |= 1; spot = -1; highlight = result.spot ?? -1; hintDepth++;
        const at = board.cells[highlight];
        if (!at) message.textContent = "Your route is ready. Press Go!";
        else if (hintDepth === 1) message.textContent = "Look at the piece marked with a sun.";
        else if (workshopMessages[board.mode]) message.textContent = workshopMessages[board.mode][2];
        else if (at.kind === "socket" && !moves[mutable.indexOf(highlight)]) message.textContent = "Pick the spare bend, then tap the sun.";
        else if (at.kind === "switch") message.textContent = "Tap the sunny switch to try its other track.";
        else if (at.kind.toLowerCase().includes("valve")) message.textContent = "Tap the sunny valve to change where water can flow.";
        else message.textContent = "Turn the sunny piece until its ends meet the path.";
      } else {
        help |= 2; message.textContent = "Thanks for playing together!";
      }
    } catch {
      if (id === version && !signal.aborted) message.textContent = "Couldn’t reach Little Garden. Your pieces are here. Try again.";
    } finally {
      if (id === version && !signal.aborted && root.isConnected) {
        busy = ""; refresh();
        if (action === "run") button(solved ? "next" : "run").focus({preventScroll:true});
      }
    }
  }
  for (const action of ["run", "hint", "parent"]) button(action).onclick = () => request(action);
  refresh();
}
