(() => {
  const room = document.querySelector("#live-room");
  const select = room.querySelector("select");
  const tiles = [...room.querySelectorAll(".live-tile")];
  if (select.value === "all" && window.matchMedia("(max-width: 719px)").matches) select.selectedIndex = 1;
  let timer, controller;

  function draw(scene, state) {
    const art = scene.querySelector(".live-art");
    if (art) renderPicture(art, state.pixels || "0".repeat(768), null);
    const trace = scene.querySelector(".live-trail");
    if (trace) {
      const ink = trace.querySelector(".live-ink");
      for (const path of trace.querySelectorAll("path")) path.setAttribute("d", trace.dataset.path || traceShapes[trace.dataset.shape]);
      const length = ink.getTotalLength();
      const distance = length * (state.percent || 0) / 100;
      ink.style.strokeDasharray = length;
      ink.style.strokeDashoffset = length - distance;
      const position = ink.getPointAtLength(distance);
      const dot = trace.querySelector("circle");
      dot.setAttribute("cx", position.x); dot.setAttribute("cy", position.y);
    }
    const typed = scene.querySelector("[data-typed]");
    if (typed) typed.textContent = state.typed || "";
    const basket = scene.querySelector("[data-basket]");
    if (basket) basket.textContent = state.count ? "🍓 ".repeat(state.count) : "Empty basket";
    const pointer = scene.querySelector(".live-pointer");
    if (pointer) {
      pointer.hidden = state.x == null || state.y == null;
      pointer.style.left = state.x + "%"; pointer.style.top = state.y + "%";
    }
    const retry = scene.querySelector("[data-retry]");
    if (retry) retry.hidden = !state.retry;
  }

  function show(tile, frame, message) {
    const status = tile.querySelector(".live-status");
    if (status.textContent !== message) status.textContent = message;
    tile.classList.toggle("is-live", Boolean(frame));
    const scene = tile.querySelector(".live-scene");
    const html = frame?.html || "";
    if (tile.sceneHTML !== html) {
      // The server renders this fragment from household-scoped curriculum and escaped text.
      scene.innerHTML = html;
      tile.sceneHTML = html;
    }
    if (frame?.state) draw(scene, frame.state);
    const response = tile.querySelector(".live-response");
    response.textContent = frame?.response || "";
    response.hidden = !frame?.response;
  }

  async function poll() {
    clearTimeout(timer);
    controller?.abort();
    if (document.hidden) return;
    const request = new AbortController();
    controller = request;
    const deadline = setTimeout(() => {
      request.abort();
      if (controller === request && !document.hidden) {
        tiles.filter(tile => !tile.hidden).forEach(tile => show(tile, null, "Connection lost · reconnecting"));
        timer = setTimeout(poll, 900);
      }
    }, 5000);
    const selection = select.value;
    const visible = tiles.filter(tile => !tile.hidden);
    try {
      const response = await fetch(room.dataset.url, {method: "POST", signal: request.signal,
        headers: {"X-CSRFToken": room.dataset.token}, body: new URLSearchParams({child: selection}), cache: "no-store"});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (request.signal.aborted) return;
      visible.forEach(tile => {
        const frame = data.children[tile.dataset.child];
        show(tile, frame, frame ? "Live" : "Waiting for an open garden");
      });
    } catch {
      if (!request.signal.aborted) visible.forEach(tile => show(tile, null, "Connection lost · reconnecting"));
    } finally {
      clearTimeout(deadline);
      if (!request.signal.aborted) timer = setTimeout(poll, 900);
    }
  }
  function switchView() {
    tiles.forEach(tile => {
      tile.hidden = select.value !== "all" && select.value !== tile.dataset.child;
      show(tile, null, "Connecting…");
    });
    poll();
  }
  select.addEventListener("change", switchView);
  document.addEventListener("visibilitychange", switchView);
  select.disabled = false;
  switchView();
})();
