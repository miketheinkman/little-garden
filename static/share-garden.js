(() => {
  const badge = document.querySelector("#live-presence");
  const form = document.querySelector("#activity");
  let watching = false;
  let pointer = null;
  let timer;
  let busy = false;

  const meadow = document.querySelector(".meadow");
  meadow?.addEventListener("pointermove", event => {
    const box = meadow.getBoundingClientRect();
    pointer = {x: Math.round(100 * (event.clientX - box.left) / box.width),
               y: Math.round(100 * (event.clientY - box.top) / box.height)};
  });
  meadow?.addEventListener("pointerleave", () => { pointer = null; });

  function scene() {
    if (!form) return {screen: "garden"};
    const data = {screen: "lesson", assignment: badge.dataset.assignment, step: badge.dataset.step};
    if (!watching) return data;
    if (document.querySelector('article [role="alert"]')) data.retry = "1";
    switch (form.dataset.kind) {
      case "draw": case "mirror": case "color": data.pixels = form.elements.pixels.value; break;
      case "type": data.typed = form.elements.answer.value.slice(0, 80); break;
      case "trace": data.percent = document.querySelector("#trail").dataset.percent || 0; break;
      case "basket": data.count = document.querySelector("#check-basket").value; break;
      case "mouse": if (pointer) Object.assign(data, pointer); break;
    }
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
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(badge.dataset.url, {
        method: "POST", signal: controller.signal, headers: {"X-CSRFToken": badge.dataset.token},
        body: new URLSearchParams(scene()), cache: "no-store"
      });
      if (!response.ok) throw new Error();
      status((await response.json()).watching);
    } catch { status(false); }
    finally {
      clearTimeout(deadline);
      busy = false;
      if (!document.hidden) timer = setTimeout(send, watching ? 650 : 2500);
    }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {clearTimeout(timer); status(false);}
    else send();
  });
  send();
})();
