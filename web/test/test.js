// Bare-bones model test page. No webcam, no pixel art: canned IMU gestures go
// in, the engine's decision (and WHICH brain made it) comes out, big and
// color-coded, with the audio right here. The fastest possible answer to
// "is the model actually changing the music?"

import { Conn } from "../shared/ws.js";
import { Clock } from "../shared/clock.js";
import { Synth } from "../shared/synth.js";
import * as P from "../shared/protocol.js";

const el = (id) => document.getElementById(id);
const conn = new Conn({ role: "stage", session: "lol1" });
const clock = new Clock((o) => conn.send(o));
const synth = new Synth(clock, null);
let seq = 0;

const COLORS = {
  rhythmic_dense: "#e5686a", contrary_motion: "#7fd1ff", sustained: "#6fcf7f",
  delayed: "#e5a23d", lower_imitation: "#c77fff", rest: "#777", generated: "#e7c583",
};

// Canned IMU bursts — the same synthetics the headless tests use, so what you
// hear here matches what the test suite asserts.
function imu(accel, gyro, ay, durMs, n) {
  const out = [], total = accel + 9.8;
  for (let i = 0; i < n; i++) {
    out.push([Math.round(i * durMs / (n - 1)), total * (i % 2 ? 1 : -1), ay, 0, gyro, 0, 0]);
  }
  return out;
}
const GESTURES = {
  "🌊 BIG WAVE → busy":        () => imu(12, 0, 0, 500, 30),
  "🍃 GENTLE → calm":          () => imu(0.3, 0, 0, 250, 10),
  "🌀 TWIST → counter-melody": () => imu(1, 250, 0, 600, 30),
  "⚡ SHARP FLICK → sting":    () => imu(12, 0, 0, 300, 18),
  "⬆ LIFT → octave up":        () => imu(2, 0, 9.0, 900, 40),
  "🌅 SWELL → 4-bar climax":   () => imu(6, 0, 8.5, 1200, 50),
};

const gwrap = el("gestures");
for (const [name, gen] of Object.entries(GESTURES)) {
  const b = document.createElement("button");
  b.textContent = name;
  b.addEventListener("click", () => {
    const frames = gen();
    const tw = Math.round(performance.now());
    conn.send({ t: P.WAND_GRAB, state: "start", tw });
    conn.send({ t: P.WAND_IMU, seq: seq++, frames });
    conn.send({ t: P.WAND_GRAB, state: "end", tw: tw + frames[frames.length - 1][0] });
    log(`sent ${name} — the answer lands within one bar (~2.4s)`);
  });
  gwrap.appendChild(b);
}

function log(msg) {
  const d = document.createElement("div");
  d.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
  el("log").prepend(d);
}

el("start").addEventListener("click", async () => {
  await synth.unlock();
  clock.attachAudio(synth.ctx);
  clock.start();
  conn.send({ t: P.ADMIN_CMD, cmd: "start" });
  log("transport started — baseline is 'sustained' until you gesture");
});
el("stop").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "stop" }));

let barCount = 0, barStart = 0, barMs = 2400;
conn.on(P.CLOCK_PONG, (m) => clock.handlePong(m));
conn.on(P.SCHED_NOTES, (m) => {
  if (m.events.length > 2) {                 // a bar batch: anchor the progress bar
    barStart = Math.min(...m.events.map((e) => e.at));
    if (lastState.bpm) barMs = 60000 / lastState.bpm * 4;
  }
  let n = 0;
  for (const e of m.events) {
    // Test page is the whole orchestra; the melody rides at exactly vel 0.9.
    if (el("mute").checked && e.vel === 0.9 && e.art === "pluck") continue;
    synth.schedule(e);
    n++;
  }
  barCount = n;
  renderMeta();
});
conn.on(P.SCHED_CANCEL, (m) => { if (m.allnotesoff) synth.panic(); });
conn.on(P.FX_TENSION, (m) => synth.setTension(m.value));
conn.on(P.FX_EXPR, (m) => { if (m.section === P.SECTION_ALL) synth.setExpression(m.semis, m.gain); });

let lastState = {};
conn.on(P.ENGINE_STATE, (m) => {
  lastState = m;
  el("choice").textContent = m.last_choice || "—";
  el("choice").style.color = COLORS[m.last_choice] || "#ddd";
  const src = m.decision_source || "?";
  el("source").textContent = src === "model" ? "🧠 MODEL decided (your trained brain)"
                                             : `${src} decided`;
  el("source").className = src;
  const g = m.gesture;
  el("feat").textContent = g
    ? `gesture felt as: energy ${g.energy.toFixed(2)} · size ${g.size.toFixed(2)} · ` +
      `vertical ${g.vertical.toFixed(2)} · rotation ${g.rotation.toFixed(2)} · ${g.duration.toFixed(2)}s`
    : "";
  log(`bar decision: ${m.last_choice} [${src}]`);
  renderMeta();
});
conn.on(P.ROSTER, (m) => {
  const eng = m.engine || {};
  if (eng.training_rows) el("meta").dataset.rows = eng.training_rows;
  renderMeta();
});

function renderMeta() {
  el("meta").textContent =
    `${lastState.song || ""} · ${lastState.bpm || ""} BPM · ${barCount} notes this batch` +
    (el("meta").dataset.rows ? ` · ${el("meta").dataset.rows} training rows harvested` : "");
}

setInterval(() => {
  if (clock.theta !== null) conn.send({ t: P.CLOCK_REPORT, theta: clock.theta, rtt: clock.rtt });
}, 2000);

(function barTick() {                         // when the bar fills, the next decision lands
  if (barStart && clock.theta !== null) {
    const p = ((clock.serverNow() - barStart) % barMs) / barMs;
    el("barpos").style.width = `${Math.max(0, Math.min(100, p * 100))}%`;
    el("barcap").textContent = "instant sting fires right away · rhythm changes in " +
      `${((1 - p) * barMs / 1000).toFixed(1)}s (the next bar line)`;
  }
  requestAnimationFrame(barTick);
})();

conn.onOpen((w) => { clock.checkEpoch(w.server_time); log("connected"); });
conn.onClose(() => log("reconnecting…"));
conn.connect();
