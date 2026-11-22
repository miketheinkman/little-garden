function startActivity(form, signal) {
  const listen = document.querySelector("#listen");
  const audio = document.querySelector(".word-station audio");
  const synth = window.speechSynthesis;
  let utterance;

  function speak(text, fallback) {
    utterance = null;
    audio?.pause();
    if (!synth || !window.SpeechSynthesisUtterance) { fallback?.(); return; }
    try {
      synth.cancel();
      const message = new SpeechSynthesisUtterance(text);
      utterance = message;
      message.rate = 0.93;
      message.pitch = 1.13;
      message.onerror = event => {
        if (utterance === message && form.isConnected && !["interrupted", "canceled"].includes(event.error)) fallback?.();
      };
      synth.speak(message);
    } catch { fallback?.(); }
  }

  if (synth && window.SpeechSynthesisUtterance) {
    listen.hidden = false;
    listen.onclick = () => speak(document.querySelector("#prompt").textContent);
  }
  if (audio) {
    const playWord = document.querySelector("[data-hear-word]");
    playWord.hidden = false;
    audio.controls = false;
    playWord.onclick = () => speak(playWord.dataset.hearWord, () => {
      audio.currentTime = 0;
      audio.play().catch(() => { audio.closest(".word-station").querySelector("details").open = true; });
    });
  }
  signal.addEventListener("abort", () => {
    utterance = null;
    synth?.cancel();
    audio?.pause();
  }, {once: true});
  const harvest = form.querySelector(".harvest");
  if (harvest) startHarvest(harvest, form);

  function answer(value) {
    if (form.inert) return;
    const field = document.createElement("input");
    field.type = "hidden";
    field.name = "answer";
    field.dataset.generatedAnswer = "";
    field.value = value;
    form.append(field);
    form.requestSubmit();
  }

  const tool = form.querySelector(".garden-tool");
  if (tool) startGardenTool(tool, form, answer, signal);

  if (form.dataset.kind === "key") {
    document.addEventListener("keydown", event => {
      if (form.inert) return;
      if (event.target.closest("a, button, input, textarea, select, [contenteditable]") && !form.contains(event.target)) return;
      if (!event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey && /^[a-z0-9]$/i.test(event.key)) {
        event.preventDefault();
        answer(event.key);
      }
    }, {signal});
  }

  const trail = document.querySelector("#trail");
  if (trail) {
    const ink = document.querySelector("#ink");
    const dot = document.querySelector("#dot");
    const shape = trail.dataset.shape;
    const strokes = traceStrokes(trail);
    let stroke = 0;
    setTraceStroke(trail, strokes, stroke);
    let length = ink.getTotalLength();
    let distance = 0, pointer = null;
    ink.style.strokeDasharray = length + " " + length;
    function paint() {
      trail.dataset.percent = Math.round(100 * (stroke + distance / length) / strokes.length);
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
    function finishStroke() {
      pointer = null;
      if (stroke + 1 === strokes.length) { answer(shape); return; }
      setTraceStroke(trail, strokes, ++stroke);
      length = ink.getTotalLength();
      ink.style.strokeDasharray = length + " " + length;
      distance = 0;
      paint();
      document.querySelector("[data-stroke-help]").textContent =
        "Stroke " + (stroke + 1) + " of " + strokes.length + ". Lift and start at the gold dot.";
    }
    paint();
    trail.onpointerdown = event => {
      if (gap(event, distance) <= 14) {
        pointer = event.pointerId;
        trail.setPointerCapture(pointer);
        if (length < 3) finishStroke();
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
      if (length - distance < 3) finishStroke();
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
      berries.textContent = count ? (berries.dataset.icon + " ").repeat(count) : "Empty " + berries.dataset.box;
      berries.setAttribute("aria-label", count + " in the " + berries.dataset.box);
      document.querySelector("#check-basket").value = count;
      take.disabled = count === 0;
      add.disabled = count === 12;
    }
    add.onclick = () => update(1);
    take.onclick = () => update(-1);
  }

  // Response time is optional evidence. Only active, visible time on this step counts.
  if (form.dataset.timing) {
    const storageKey = "garden-key-time-" + form.dataset.timing;
    let elapsed = 0;
    try { elapsed = Number(sessionStorage.getItem(storageKey)) || 0; } catch {}
    let since = null;
    function pause() {
      if (since !== null) elapsed += performance.now() - since;
      since = null;
      try { sessionStorage.setItem(storageKey, String(Math.round(elapsed))); } catch {}
    }
    function syncClock() {
      pause();
      if (!document.hidden && document.hasFocus()) since = performance.now();
    }
    document.addEventListener("visibilitychange", syncClock, {signal});
    window.addEventListener("focus", syncClock, {signal});
    window.addEventListener("blur", pause, {signal});
    window.addEventListener("pagehide", pause, {signal});
    signal.addEventListener("abort", pause, {once: true});
    window.addEventListener("pageshow", syncClock, {signal});
    syncClock();
    let typed = false;
    let assisted = false;
    form.addEventListener("input", event => {
      if (event.inputType === "insertText" && event.data?.length === 1) typed = true;
      else if (!event.inputType?.startsWith("delete")) assisted = true;
    });
    form.addEventListener("formdata", event => {
      // The key handler creates a hidden answer; a clicked onscreen choice is untimed.
      const physical = form.dataset.kind === "key" && form.querySelector('input[type=hidden][name=answer]');
      if (physical || (form.dataset.kind === "type" && typed && !assisted)) {
        pause();
        event.formData.set("active_ms", String(Math.round(elapsed)));
      }
    });
  }
}
