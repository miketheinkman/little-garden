// Paint a simulated board identically in the player and the live parent view.
const workshopArrows = ["↑", "→", "↓", "←"];
const workshopMessages = {
  light: ["Follow the beam…", "Every light is shining!", "Turn or place the marked mirror."],
  bridge: ["Crossing the stream…", "Across the water!", "Try a different plank length or direction on this water square."],
  delivery: ["Follow the commands…", "All parcels delivered!", "Change the marked arrow to guide the next move."],
  gears: ["Turning the crank…", "The spinner is turning the right way!", "Change the marked gear or crank."],
  gates: ["Checking the path…", "Through the gates!", "Flip the marked switch and watch its matching locks."]
};

function paintWorkshop(root, board, nodes, mutable, token, moves, trace, spot, hint) {
  const {cells, mode, width} = board;
  const start = cells.findIndex(c => c.kind === "source");
  const states = cells.map((cell, i) => moves[mutable.indexOf(i)] || 0);
  const leverOn = kind => states[cells.findIndex(c => c.kind === kind)] === 1;
  const arrows = workshopArrows;
  const actor = root.dataset.actor || "🐞";
  token.hidden = mode === "gears" || mode === "light";
  token.textContent = actor;
  const at = trace.at(-1) ?? start;
  token.style.transform = 'translate(' + (at % width * 100) + '%, ' + (Math.floor(at / width) * 100) + '%)';
  let ray = root.querySelector(".workshop-ray");
  if (mode === "light") {
    if (!ray) {
      ray = document.createElementNS("http://www.w3.org/2000/svg","svg");
      ray.classList.add("workshop-ray");
      ray.setAttribute("aria-hidden","true");
      ray.setAttribute("viewBox", "0 0 " + width + " " + cells.length/width);
      ray.append(document.createElementNS(ray.namespaceURI,"polyline"));
      root.querySelector(".route-grid").append(ray);
    }
    ray.firstChild.setAttribute("points", trace.map(i => (i%width+.5)+","+(Math.floor(i/width)+.5)).join(" "));
  }
  cells.forEach((cell,i) => {
    const node = nodes[i], state = states[i];
    let icon = "", label = cell.kind, badge = "";
    const live = trace.includes(i);
    switch (cell.kind) {
      case "source":
        icon = {light:"🔦",bridge:"🏁",delivery:"📮",gears:"⚙︎",gates:"🏁"}[mode];
        label = mode === "gears" ? "crank" : "start";
        badge = mode === "gears" ? (cells[start].clockwise !== Boolean(state) ? "↻":"↺") : arrows[cell.angle];
        break;
      case "goal":
        icon = {light:"⭐",bridge:root.dataset.landmark,delivery:"🏁",gears:"🌼",gates:root.dataset.landmark}[mode];
        label = mode === "gears" ? "spinner" : "destination";
        badge = mode === "gears" ? (board.clockwise ? "↻":"↺") : "⚑";
        break;
      case "mirror": case "mirrorMount": {
        const empty = cell.kind === "mirrorMount" && !state;
        const back = (cell.angle + state - Number(cell.kind === "mirrorMount")) % 2;
        icon = empty ? "＋" : back ? "╲" : "╱";
        label = empty ? "empty mirror mount" : back ? "mirror sloping down to the right" : "mirror sloping up to the right";
        break;
      }
      case "bridgePeg": {
        const length = state % 2 ? 1 : 2;
        const direction = state <= 2 ? cell.angle : cell.perpendicular;
        icon = state ? "" : "＋";
        label = state ? length + " space plank " + routeDirections[direction] : "empty bridge landing";
        badge = state ? length + arrows[direction] : "";
        if (state) {
          node.style.setProperty("--plank-length", length);
          node.style.setProperty("--plank-turn", (direction-1)*90+"deg");
        }
        break;
      }
      case "arrow": icon = arrows[(cell.angle+state)%4]; label = "command " + routeDirections[(cell.angle+state)%4]; break;
      case "leverA": case "leverB":
        icon = cell.kind === "leverA" ? "●" : "▲"; badge = state ? "ON":"OFF";
        label = (cell.kind === "leverA" ? "circle":"triangle") + " switch " + badge; break;
      case "gateA": case "gateB": case "gateBoth": {
        const open = (cell.kind === "gateB" || leverOn("leverA")) && (cell.kind === "gateA" || leverOn("leverB"));
        icon = open ? "🔓" : "🔒";
        badge = {gateA:"●",gateB:"▲",gateBoth:"●▲"}[cell.kind];
        label = (open ? "open " : "closed ") + {gateA:"circle gate",gateB:"triangle gate",gateBoth:"double lock"}[cell.kind];
        break;
      }
      case "gearPeg": icon = state ? "⚙︎":"＋"; label = state ? "mounted gear" : "empty gear peg"; break;
      case "gear": icon = "⚙︎"; break;
      case "parcel": icon = live ? "✓":"📦"; break;
      case "lantern": icon = live ? "💡":"🏮"; break;
      case "water": icon = "≈"; break;
      case "rock": icon = "🪨"; break;
      case "island": icon = "🌱"; break;
    }
    node.dataset.kind = cell.kind;
    node.dataset.placed = String(Boolean(state));
    node.classList.toggle("workshop-live", live);
    node.classList.toggle("is-hint", i === hint);
    node.classList.toggle("is-stop", i === spot);
    node.classList.toggle("is-arrived", cell.kind === "goal" && live);
    if (i === hint || i === spot) node.dataset.marker = i === hint ? "☀" : "!";
    else delete node.dataset.marker;
    let face = node.querySelector(".workshop-face");
    if (!face) {
      face = document.createElement("span");
      face.className = "workshop-face"; face.setAttribute("aria-hidden","true"); node.append(face);
    }
    face.textContent = icon;
    if (mode === "gears" && live) {
      const odd = Math.abs(i%width-start%width + Math.floor(i/width)-Math.floor(start/width)) % 2;
      face.style.animationDirection = Boolean(cells[start].clockwise ^ states[start] ^ odd) ? "normal" : "reverse";
    }
    let mark = node.querySelector(".route-mark");
    if (badge) {
      if (!mark) { mark = document.createElement("small"); mark.className = "route-mark"; node.append(mark); }
      mark.textContent = badge;
    } else if (mark) mark.remove();
    node.setAttribute("aria-label", label + (badge && mode === "gears" ? (badge === "↻" ? " clockwise" : " counterclockwise") : "") +
      ", row " + (Math.floor(i/width)+1) + ", column " + (i%width+1));
    if (node.tagName !== "BUTTON") node.setAttribute("role","img");
  });
}
