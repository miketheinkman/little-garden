function startActivity(form, signal) {
  const directions = document.querySelector("#directions-audio");
  const call = document.querySelector("[data-call-audio]");
  const word = document.querySelector(".word-station audio");
  const status = document.querySelector("#audio-status");
  const stopButton = document.querySelector("#stop-audio");
  const listen = document.querySelector("#listen");
  const wordButton = document.querySelector("[data-hear-word]");
  const callButton = document.querySelector("[data-hear-call]");
  const autoplay = form.hasAttribute("data-autoplay-directions");
  let playback = 0;
  let followDirections = false;

  function stopPlayback() {
    playback++;
    followDirections = false;
    for (const audio of [directions, word, call]) audio?.pause();
    stopButton.hidden = true;
  }

  async function playClip(audio, button, follow = false) {
    stopPlayback();
    const attempt = playback;
    followDirections = follow;
    status.hidden = true;
    for (const control of [listen, wordButton, callButton]) control?.classList.remove("needs-tap");
    try {
      if (audio.error) audio.load();
      audio.currentTime = 0;
      await audio.play();
      if (attempt === playback && !audio.paused) stopButton.hidden = false;
    } catch (error) {
      if (attempt !== playback || !form.isConnected || signal.aborted) return;
      followDirections = false;
      if (error.name === "NotAllowedError") {
        button.classList.add("needs-tap");
        status.textContent = audio === directions ? "Tap the speaker to hear directions." : "Tap the headphones to listen.";
      } else {
        if (word && audio === word) word.closest(".word-station").querySelector("details").open = true;
        status.textContent = audio === call ? "Audio unavailable. Open the sound clue or try again." : audio === word ? "Audio unavailable. The word is shown below." : "Audio unavailable. Read the directions above.";
      }
      status.hidden = false;
    }
  }

  for (const [button, audio] of [[listen, directions], [wordButton, word], [callButton, call]]) {
    if (!button || !audio) continue;
    button.hidden = false;
    audio.controls = false;
    button.onclick = () => playClip(audio, button, autoplay && audio === directions);
    audio.addEventListener("pause", () => {
      if ([directions, word, call].every(clip => !clip || clip.paused)) stopButton.hidden = true;
    }, {signal});
  }
  directions.addEventListener("ended", () => {
    if (followDirections && !document.hidden && form.isConnected && (word || call)) {
      playClip(word || call, wordButton || callButton);
    }
  }, {signal});
  stopButton.onclick = stopPlayback;
  signal.addEventListener("abort", stopPlayback, {once: true});
  window.addEventListener("pagehide", stopPlayback, {signal});
  form.addEventListener("submit", stopPlayback, {signal});
  document.querySelector(".skip-step")?.addEventListener("submit", stopPlayback, {signal});
  let waitingForVisibility = autoplay;
  function startWhenVisible() {
    if (document.hidden) stopPlayback();
    else if (waitingForVisibility) {
      waitingForVisibility = false;
      playClip(directions, listen, true);
    }
  }
  document.addEventListener("visibilitychange", startWhenVisible, {signal});
  startWhenVisible();
  const route = form.querySelector(".route-game");
  if (route) startRoutePuzzle(route, form, signal);
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
