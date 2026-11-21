const form = document.querySelector("#activity");
const listen = document.querySelector("#listen");
if (window.speechSynthesis) {
  listen.hidden = false;
  listen.onclick = () => {
    speechSynthesis.cancel();
    const message = new SpeechSynthesisUtterance(document.querySelector("#prompt").textContent);
    message.rate = 0.93;
    message.pitch = 1.13;
    speechSynthesis.speak(message);
  };
}

function answer(value) {
  const field = document.createElement("input");
  field.type = "hidden";
  field.name = "answer";
  field.value = value;
  form.append(field);
  form.requestSubmit();
}

if (form.dataset.kind === "key") {
  document.addEventListener("keydown", event => {
    if (event.target.closest("a, button, input, textarea, select, [contenteditable]") && !form.contains(event.target)) return;
    if (!event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey && /^[a-z0-9]$/i.test(event.key)) {
      event.preventDefault();
      answer(event.key);
    }
  });
}

const trail = document.querySelector("#trail");
if (trail) {
  const shapes = {
    W: "M35 30L64 120L98 61L134 120L162 30", Z: "M55 25H145L55 125H145",
    N: "M60 125V25L140 125V25", 3: "M60 38Q155 -5 122 65L94 75Q165 80 125 118Q95 140 60 119",
    4: "M128 125V26L61 93H150", 7: "M55 27H147L85 126",
    river: "M22 112 Q70 12 114 66 T180 38", stream: "M24 25 C180 12 180 65 104 75 S30 130 178 122",
    line: "M28 75H172", hill: "M24 110Q100 -16 176 110",
    L: "M74 25V125H134", V: "M55 25L100 125L145 25",
    O: "M100 22C33 22 33 128 100 128C167 128 167 22 100 22",
    1: "M76 48L102 24V126", 2: "M58 49C67 0 162 18 132 65L59 125H146"
  };
  const ink = document.querySelector("#ink");
  const dot = document.querySelector("#dot");
  const shape = trail.dataset.shape;
  for (const path of trail.querySelectorAll("path")) path.setAttribute("d", trail.dataset.path || shapes[shape]);
  const length = ink.getTotalLength();
  let distance = 0, pointer = null;
  ink.style.strokeDasharray = length + " " + length;
  function paint() {
    const at = ink.getPointAtLength(distance);
    dot.setAttribute("cx", at.x);
    dot.setAttribute("cy", at.y);
    ink.style.strokeDashoffset = length - distance;
  }
  function gap(event, n) {
    const at = ink.getPointAtLength(n);
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(trail.getScreenCTM().inverse());
    return Math.hypot(at.x - p.x, at.y - p.y);
  }
  paint();
  trail.onpointerdown = event => {
    if (gap(event, distance) <= 14) {
      pointer = event.pointerId;
      trail.setPointerCapture(pointer);
    }
  };
  trail.onpointermove = event => {
    if (event.pointerId !== pointer) return;
    let best = distance, closest = 13;
    for (let n = distance; n <= Math.min(length, distance + 26); n++) {
      const delta = gap(event, n);
      if (delta < closest) { best = n; closest = delta; }
    }
    distance = best;
    paint();
    if (length - distance < 3) { pointer = null; answer(shape); }
  };
  trail.onpointerup = trail.onpointercancel = () => { pointer = null; };
}

if (form.dataset.kind === "basket") {
  let count = 0;
  const add = document.querySelector("#add-berry");
  const take = document.querySelector("#take-berry");
  function update(change) {
    count += change;
    const berries = document.querySelector("#berries");
    berries.textContent = count ? "🍓 ".repeat(count) : "Empty basket";
    berries.setAttribute("aria-label", count + " berries in basket");
    document.querySelector("#check-basket").value = count;
    take.disabled = count === 0;
    add.disabled = count === 12;
  }
  add.onclick = () => update(1);
  take.onclick = () => update(-1);
}
