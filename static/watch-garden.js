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

  function stopPeer(tile) {
    tile.peer?.close();
    tile.peer = null;
    tile.direct = null;
  }
  function fresh(tile) {
    return tile.peer?.channel?.readyState === "open" && tile.direct && performance.now() - tile.received < 2200;
  }
  function display(tile) {
    const frame = tile.frame;
    if (!frame) { show(tile, null, "Waiting for an open garden"); return; }
    if (fresh(tile)) show(tile, {...frame, state: tile.direct}, "Live · Direct");
    else show(tile, frame, "Live · Server relay");
  }
  function connect(tile, source) {
    if (tile.source !== source) {
      stopPeer(tile);
      tile.source = source;
      tile.retryAfter = 0;
    }
    if (!source || !window.RTCPeerConnection || tile.hidden) return;
    const now = performance.now();
    if (tile.peer && !fresh(tile) &&
        (tile.direct || now - tile.peer.started > 7500)) {
      stopPeer(tile);
      tile.retryAfter = now + 10000;
    }
    if (tile.peer || now < tile.retryAfter) return;
    try {
      const peer = new GardenPeer(gardenPeerId());
      tile.peer = peer;
      peer.offer(data => {
        if (tile.peer !== peer || !tile.frame || tile.hidden || document.hidden || !data || typeof data !== "object") return;
        // Peer input is data only. Markup and the active step always come from Django.
        const bound = (v, max) => Math.max(0, Math.min(max, parseInt(v, 10) || 0));
        tile.direct = {
          typed: typeof data.typed === "string" ? data.typed.slice(0, 80) : "",
          pixels: typeof data.pixels === "string" && /^[0-5]{768}$/.test(data.pixels) ? data.pixels : "",
          retry: data.retry === "1", count: bound(data.count, 12), percent: bound(data.percent, 100),
          x: data.x == null ? null : bound(data.x, 100), y: data.y == null ? null : bound(data.y, 100)
        };
        tile.received = performance.now();
        display(tile);
      }).catch(() => { if (tile.peer === peer) { stopPeer(tile); tile.retryAfter = performance.now() + 10000; } });
    } catch { tile.retryAfter = now + 10000; }
  }
  function signal(tile) {
    if (!tile.peer) return {};
    return {id: tile.peer.id, source: tile.source, direct: Boolean(fresh(tile)),
            offer: tile.peer.pc.remoteDescription ? "" : tile.peer.sdp};
  }
  function receive(tile, frame, reply) {
    if (frame?.reuse && frame.source === tile.frame?.source) {
      frame = {...tile.frame, response: frame.response};
    }
    tile.frame = frame;
    connect(tile, frame?.source || "");
    const peer = tile.peer;
    if (reply?.answer && peer && !peer.pc.remoteDescription && !peer.applying) {
      peer.applying = true;
      peer.pc.setRemoteDescription({type: "answer", sdp: reply.answer}).catch(() => {
        if (tile.peer === peer) { stopPeer(tile); tile.retryAfter = performance.now() + 10000; }
      });
    }
    display(tile);
  }
  function disconnected(tile) {
    stopPeer(tile);
    tile.frame = null;
    show(tile, null, "Connection lost · reconnecting");
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
        tiles.filter(tile => !tile.hidden).forEach(disconnected);
        timer = setTimeout(poll, 900);
      }
    }, 5000);
    const selection = select.value;
    const visible = tiles.filter(tile => !tile.hidden);
    const signals = Object.fromEntries(visible.map(tile => [tile.dataset.child, signal(tile)]));
    try {
      const response = await fetch(room.dataset.url, {method: "POST", signal: request.signal,
        headers: {"X-CSRFToken": room.dataset.token}, body: new URLSearchParams({child: selection, signals: JSON.stringify(signals)}), cache: "no-store"});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (request.signal.aborted) return;
      visible.forEach(tile => {
        const frame = data.children[tile.dataset.child];
        receive(tile, frame, data.signals?.[tile.dataset.child]);
      });
    } catch {
      if (!request.signal.aborted) visible.forEach(disconnected);
    } finally {
      clearTimeout(deadline);
      if (!request.signal.aborted) timer = setTimeout(poll, 900);
    }
  }
  function switchView() {
    tiles.forEach(tile => {
      tile.hidden = select.value !== "all" && select.value !== tile.dataset.child;
      if (tile.hidden || document.hidden) { stopPeer(tile); tile.frame = null; }
      show(tile, null, "Connecting…");
    });
    poll();
  }
  window.addEventListener("pagehide", () => tiles.forEach(stopPeer));
  select.addEventListener("change", switchView);
  document.addEventListener("visibilitychange", switchView);
  select.disabled = false;
  switchView();
})();
