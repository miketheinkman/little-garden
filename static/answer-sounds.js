// One instrument per tab. Prepare it during the answer gesture, before the server replies.
let answerAudioContext;
function startAnswerSounds(signal) {
  const control = document.querySelector("#answer-sounds");
  const AudioEngine = window.AudioContext || window.webkitAudioContext;
  const preference = "little-garden-answer-sounds";
  let output, ready;
  let generation = 0;
  if (AudioEngine) control.parentElement.hidden = false;
  try { control.checked = localStorage.getItem(preference) !== "off"; } catch {}

  function silence() {
    generation++;
    if (output) output.disconnect();
    output = null;
  }
  function prepare() {
    silence();
    if (!control.checked || !AudioEngine || document.hidden) return;
    try {
      answerAudioContext ??= new AudioEngine();
      ready = answerAudioContext.state === "running" ? null : answerAudioContext.resume().catch(() => {});
    } catch {} // Visual feedback also works on devices without audio output.
  }
  control.addEventListener("change", () => {
    if (!control.checked) silence();
    try { localStorage.setItem(preference, control.checked ? "on" : "off"); } catch {}
  }, {signal});
  document.addEventListener("play", silence, {capture:true, signal});
  document.addEventListener("visibilitychange", () => { if (document.hidden) silence(); }, {signal});
  window.addEventListener("pagehide", silence, {signal});
  signal.addEventListener("abort", silence, {once:true});

  async function play(result) {
    const ctx = answerAudioContext;
    if (ready && ctx?.state !== "running") {
      const attempt = generation, requested = performance.now();
      await ready;
      if (attempt !== generation || performance.now() - requested > 350) return;
    }
    if (!control.checked || signal.aborted || document.hidden || ctx?.state !== "running") return;
    if ([...document.querySelectorAll("audio")].some(clip => !clip.paused && !clip.ended)) return;
    silence();
    const bus = ctx.createGain();
    bus.gain.value = 0.12;
    bus.connect(ctx.destination);
    output = bus;
    const now = ctx.currentTime;
    // A rising C-major flourish, or a soft two-note wobble with a little upward curl.
    const retry = result === "retry";
    const notes = retry
      ? [[0, 392, 330, .15], [.15, 294, 330, .23]]
      : [[0, 523.25, 523.25, .16], [.10, 659.25, 659.25, .18], [.21, 783.99, 783.99, .33]];
    notes.forEach(([offset, from, to, duration], index) => {
      const start = now + offset;
      const voice = ctx.createOscillator();
      const envelope = ctx.createGain();
      voice.type = retry ? "sine" : "triangle";
      voice.frequency.setValueAtTime(from, start);
      voice.frequency.exponentialRampToValueAtTime(to, start + duration * .8);
      envelope.gain.setValueAtTime(0, start);
      envelope.gain.linearRampToValueAtTime(.8, start + .015);
      envelope.gain.exponentialRampToValueAtTime(.001, start + duration);
      voice.connect(envelope);
      envelope.connect(bus);
      voice.onended = () => {
        voice.disconnect();
        envelope.disconnect();
        if (index === notes.length - 1 && output === bus) silence();
      };
      voice.start(start);
      voice.stop(start + duration);
    });
  }
  return {prepare, play, silence};
}
