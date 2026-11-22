(() => {
  let badge = document.querySelector("#live-presence");
  let form = document.querySelector("#activity");
  let watching = false;
  let pointer = null;
  let timer;
  let busy = false;
  const source = window.RTCPeerConnection && typeof GardenPeer === "function" && window.crypto?.getRandomValues ? gardenPeerId() : "";
  const peers = new Map();
  let relay = true;
  let leaseUntil = 0;
  let lastPayload = "";
  let lastSent = 0;
  let frameTimer;

  function closePeer(id) {
    peers.get(id)?.close();
    peers.delete(id);
    if (!peers.size) { clearInterval(frameTimer); frameTimer = null; }
  }
  function stopDirect() {
    for (const id of peers.keys()) closePeer(id);
    relay = true;
    leaseUntil = 0;
  }
  function match(result) {
    if (!source || !result.watching || document.hidden) { stopDirect(); return; }
    leaseUntil = performance.now() + 6000;
    relay = result.relay !== false;
    for (const id of peers.keys()) if (!result.allowed?.includes(id)) closePeer(id);
    const offer = result.offer;
    if (!offer || peers.has(offer.id) || peers.size >= 16) return;
    try {
      const peer = new GardenPeer(offer.id);
      peers.set(peer.id, peer);
      if (!frameTimer) frameTimer = setInterval(directFrames, 120);
      peer.answer(offer.sdp).catch(() => closePeer(peer.id));
    } catch { /* The server relay stays available. */ }
  }
  function directFrames() {
    if (!watching || document.hidden || !peers.size || performance.now() >= leaseUntil) return;
    const payload = JSON.stringify(activityState());
    const now = performance.now();
    if (payload === lastPayload && now - lastSent < 600) return;
    lastPayload = payload;
    lastSent = now;
    for (const peer of peers.values()) {
      if (peer.channel?.readyState === "open" && peer.channel.bufferedAmount < 8192) {
        try { peer.channel.send(payload); } catch { closePeer(peer.id); }
      }
    }
  }
  window.addEventListener("pagehide", stopDirect);

  function sceneKey() {
    return form ? badge.dataset.assignment + ":" + badge.dataset.step : "garden";
  }
  document.addEventListener("pointermove", event => {
    const meadow = event.target.closest(".meadow");
    if (!meadow) { pointer = null; return; }
    const box = meadow.getBoundingClientRect();
    pointer = {x: Math.round(100 * (event.clientX - box.left) / box.width),
               y: Math.round(100 * (event.clientY - box.top) / box.height)};
  });
  document.addEventListener("pointerout", event => {
    if (!event.relatedTarget || !event.relatedTarget.closest?.(".meadow")) pointer = null;
  });

  function activityState() {
    const data = {scene: sceneKey()};
    if (!form || !watching) return data;
    if (document.querySelector('#native-retry, #answer-feedback .retry-note')) data.retry = "1";
    const party = document.querySelector("#answer-feedback .answer-party");
    if (party) data.celebration = party.dataset.result;
    switch (form.dataset.kind) {
      case "draw": case "mirror": case "color": data.pixels = form.elements.pixels.value; break;
      case "type": data.typed = form.elements.answer.value.slice(0, 80); break;
      case "trace": data.percent = document.querySelector("#trail").dataset.percent || 0; break;
      case "basket": data.count = document.querySelector("#check-basket").value; break;
      case "mouse": if (pointer) Object.assign(data, pointer); break;
    }
    return data;
  }
  function broadcast() {
    const data = form ? {screen: "lesson", assignment: badge.dataset.assignment, step: badge.dataset.step}
                      : {screen: "garden"};
    if (!source) return Object.assign(data, activityState());
    data.source = source;
    data.peers = [...peers.keys()].join(",");
    for (const peer of peers.values()) {
      if (peer.sdp && peer.channel?.readyState !== "open") {
        data.answer = JSON.stringify({id: peer.id, sdp: peer.sdp});
        break;
      }
    }
    if (relay) Object.assign(data, activityState());
    else data.metadata = "1";
    return data;
  }
  function status(active) {
    watching = active;
    const label = active ? "Your parent is watching along." : "Your parent can watch this garden.";
    badge.classList.toggle("watching", active);
    if (badge.textContent !== label) badge.textContent = label;
  }
  async function send() {
    clearTimeout(timer);
    if (document.hidden || busy) return;
    busy = true;
    const sentBadge = badge;
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(badge.dataset.url, {
        method: "POST", signal: controller.signal, headers: {"X-CSRFToken": badge.dataset.token},
        body: new URLSearchParams(broadcast()), cache: "no-store"
      });
      if ([401, 403].includes(response.status) || response.redirected) {
        status(false);
        stopDirect();
        return;
      }
      if (!response.ok) throw new Error();
      const result = await response.json();
      status(result.watching && !document.hidden);
      match(result);
    } catch {
      if (badge === sentBadge && performance.now() >= leaseUntil) { status(false); stopDirect(); }
    }
    finally {
      clearTimeout(deadline);
      busy = false;
      if (!document.hidden) timer = setTimeout(send, badge !== sentBadge ? 0 : watching ? 650 : 2500);
    }
  }
  document.addEventListener("garden-screen", () => {
    badge = document.querySelector("#live-presence");
    form = document.querySelector("#activity");
    pointer = null;
    status(watching);
    directFrames();
    send();
  });
  document.addEventListener("garden-answer", () => { directFrames(); send(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {clearTimeout(timer); status(false); stopDirect();}
    else send();
  });
  send();
})();
