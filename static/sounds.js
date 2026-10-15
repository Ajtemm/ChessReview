// Zvukovi poteza napravljeni preko Web Audio API-ja (bez audio fajlova):
// "move" - kratak drveni klik, "capture" - jači dvostruki klik, "check" - klik i zvonce

let ctx = null;
let noise = null;
let muted = false;

const MUTE_KEY = "chess-review-muted";
try {
  muted = localStorage.getItem(MUTE_KEY) === "1";
} catch {
  // localStorage nije dostupan (privatni prozor i sl.) - zvuk ostaje uključen
}

export function isMuted() {
  return muted;
}

export function setMuted(value) {
  muted = value;
  try {
    localStorage.setItem(MUTE_KEY, value ? "1" : "0");
  } catch {
    // podešavanje se tada ne pamti, ali radi do zatvaranja stranice
  }
}

// AudioContext pravimo tek na prvi zvuk (browser ga dozvoljava tek posle klika/tastera)
function audio() {
  if (!ctx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    ctx = new Ctx();
    // Beli šum od 0.2 s, osnova za zvuk udarca figure o tablu
    noise = ctx.createBuffer(1, ctx.sampleRate * 0.2, ctx.sampleRate);
    const data = noise.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

// Kratak udarac: filtrirani šum (drvo) + nizak ton (telo table)
function knock(at, { pitch = 1800, q = 1.2, volume = 0.6, thump = 170, length = 0.06 } = {}) {
  const src = ctx.createBufferSource();
  src.buffer = noise;
  const filter = ctx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = pitch;
  filter.Q.value = q;
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(volume, at);
  gain.gain.exponentialRampToValueAtTime(0.001, at + length);
  src.connect(filter).connect(gain).connect(ctx.destination);
  src.start(at);
  src.stop(at + length + 0.02);

  const osc = ctx.createOscillator();
  osc.type = "sine";
  osc.frequency.setValueAtTime(thump, at);
  osc.frequency.exponentialRampToValueAtTime(thump * 0.6, at + length);
  const body = ctx.createGain();
  body.gain.setValueAtTime(volume * 0.8, at);
  body.gain.exponentialRampToValueAtTime(0.001, at + length * 1.3);
  osc.connect(body).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + length * 1.3 + 0.02);
}

// Kratko zvonce za šah
function chime(at, freq, volume = 0.18, length = 0.22) {
  const osc = ctx.createOscillator();
  osc.type = "triangle";
  osc.frequency.value = freq;
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(volume, at + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.001, at + length);
  osc.connect(gain).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + length + 0.02);
}

export function playSound(type) {
  if (muted) return;
  const ac = audio();
  if (!ac) return;
  const t = ac.currentTime + 0.005;
  if (type === "capture") {
    knock(t, { pitch: 1300, q: 0.9, volume: 0.85, thump: 130, length: 0.08 });
    knock(t + 0.045, { pitch: 2200, q: 1.5, volume: 0.45, thump: 200, length: 0.05 });
  } else if (type === "check") {
    knock(t);
    chime(t + 0.03, 988);
    chime(t + 0.11, 1319);
  } else {
    knock(t);
  }
}
