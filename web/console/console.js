// Maestro Console — the whole show on one workstation screen.
//
//   LEFT   the score: one piano-roll lane per instrument in the loaded song
//   CENTER the live camera-wand (your hand conducts) with each phone connecting to it
//   RIGHT  the live gesture read-out + wand state + what your last move did
//   BOTTOM a live piano roll of every note sounding, scrolling under a playhead
//
// It connects once as `stage` (roster + sched.notes + engine.state, and it can
// drive transport). The camera in the middle is the existing hand-tracking wand
// (../cvwand/) embedded in an iframe — it opens its own wand connection, so the
// wand sprite/gestures light up here via the roster + engine.state. When no phone
// has joined, this screen is also the orchestra (plays the SECTION_ALL stream).

import { Conn } from "../shared/ws.js";
import { Clock } from "../shared/clock.js";
import { Synth } from "../shared/synth.js";
import * as P from "../shared/protocol.js";

const params = new URLSearchParams(location.search);
const session = params.get("s") || "lol1";
const el = (id) => document.getElementById(id);

// scientific pitch -> midi (sched.notes carry e.g. "C4")
const SEMI = { C: 0, "C#": 1, D: 2, "D#": 3, E: 4, F: 5, "F#": 6, G: 7, "G#": 8, A: 9, "A#": 10, B: 11 };
const noteToMidi = (n) => { const m = /^([A-G]#?)(-?\d+)$/.exec(n || ""); return m ? (parseInt(m[2], 10) + 1) * 12 + SEMI[m[1]] : 60; };

const NICE = { lower_imitation: "Lower imitation", contrary_motion: "Contrary motion", sustained: "Sustained chord",
  delayed: "Delayed echo", rhythmic_dense: "Rhythmic — busy", rhythmic: "Rhythmic — busy", rest: "Rest — silence" };

// section id -> stable colour (shared with the other stage views); drums grey.
const PALETTE = ["#e7c583", "#7fd1ff", "#6fcf7f", "#e58a6a", "#c79bff", "#ffd76a", "#79d6c0"];
function colorFor(section, drum) {
  if (drum) return "#8a8378";
  if (section === "all" || !section) return "#e7c583";
  let h = 0; for (const c of section) h = (h * 31 + c.charCodeAt(0)) % PALETTE.length;
  return PALETTE[h];
}

let conn = null, clock = null, synth = null;
let started = false, camStarted = false, audioReady = false;
let sections = [];              // latest connected sections
let readySections = 0;
const notes = [];              // {at, dur, pitch, color} for the bottom roll
const seen = new Set();
const rowEls = new Map();       // section id -> {row, dot} for note pulses
let lastChoice = null;

// ── phones (center list + dots overlay) ──────────────────────────────────────
function dotX(s, i, n) {
  // Placed phones sit by their real azimuth (-75°..+75° -> 6%..94%); unplaced
  // ones fan out evenly so they never stack on top of each other.
  if (s.placed) return 50 + Math.max(-75, Math.min(75, s.azimuth_deg)) / 75 * 44;
  return n <= 1 ? 50 : 8 + 84 * (i / (n - 1));
}

function renderRoster(m) {
  sections = (m.sections || []).filter((s) => s.connected);
  readySections = sections.filter((s) => s.ready).length;
  el("pcount").textContent = sections.length;

  const w = m.wand || {};
  el("wanddot").classList.toggle("ok", !!w.connected);
  el("wandvar").textContent = w.connected ? w.variant : "—";
  wandText(!!w.connected, w.variant);

  // clock spread across ready, synced phones
  const th = sections.filter((s) => s.ready && s.theta != null).map((s) => s.theta);
  el("spread").textContent = th.length >= 2 ? (Math.max(...th) - Math.min(...th)).toFixed(0) + "ms"
    : (readySections ? "sync…" : "laptop");

  // phone rows
  const box = el("phones");
  el("phonesempty").hidden = sections.length > 0;
  rowEls.clear();
  box.querySelectorAll(".prow").forEach((n) => n.remove());
  sections.forEach((s) => {
    const row = document.createElement("div");
    row.className = "prow";
    const col = colorFor(s.id, false);
    const synced = s.ready && s.theta != null;
    row.innerHTML =
      `<span class="sw" style="background:${col}"></span>` +
      `<span class="id">${s.id}</span>` +
      `<span class="inst">${s.instrument}${s.muted ? ' <span class="mut">muted</span>' : ""}</span>` +
      (s.connected
        ? `<span class="sync${synced ? "" : " wait"}">${synced ? "● " + s.theta.toFixed(0) + "ms" : "○ waiting"}</span>`
        : `<span class="off">● dropped</span>`);
    box.appendChild(row);
    rowEls.set(s.id, { row });
  });

  // dots overlaid on the camera
  const dots = el("dots");
  dots.innerHTML = "";
  sections.forEach((s, i) => {
    const d = document.createElement("div");
    d.className = "pdot";
    d.style.left = dotX(s, i, sections.length) + "%";
    d.innerHTML = `<div class="c" style="background:${colorFor(s.id, false)}"></div><div class="t">${s.id}</div>`;
    dots.appendChild(d);
    rowEls.get(s.id).dot = d;
  });

  applyEngine(m.engine);
}

// pulse a phone's row + dot the instant one of its notes sounds
function pulse(section) {
  const r = rowEls.get(section);
  const targets = section === P.SECTION_ALL ? [...rowEls.values()] : (r ? [r] : []);
  targets.forEach((t) => {
    t.row.classList.add("hit"); t.dot && t.dot.classList.add("hit");
    setTimeout(() => { t.row.classList.remove("hit"); t.dot && t.dot.classList.remove("hit"); }, 140);
  });
}

// ── engine state: gesture bars, last action, tempo, now-playing ──────────────
let tempoDragging = false;
el("tempo").addEventListener("pointerdown", () => (tempoDragging = true));
el("tempo").addEventListener("pointerup", () => (tempoDragging = false));

function bar(id, v, max) { el("f-" + id).style.width = Math.max(0, Math.min(1, v / max)) * 100 + "%"; }
function applyEngine(eng) {
  if (!eng) return;
  el("bpm").textContent = Math.round(eng.bpm);
  if (!tempoDragging) el("tempo").value = Math.round(eng.bpm);
  el("songname").textContent = eng.song || "";
  renderLanes(eng.tracks || []);

  const g = eng.gesture;
  if (g) {
    el("v-energy").textContent = (g.energy ?? 0).toFixed(2); bar("energy", g.energy ?? 0, 1);
    el("v-size").textContent = (g.size ?? 0).toFixed(2); bar("size", g.size ?? 0, 1);
    el("v-vertical").textContent = (g.vertical ?? 0).toFixed(2); bar("vertical", Math.abs(g.vertical ?? 0), 1);
    el("v-rotation").textContent = (g.rotation ?? 0).toFixed(2); bar("rotation", g.rotation ?? 0, 1);
    el("v-duration").textContent = (g.duration ?? 0).toFixed(1) + "s"; bar("duration", g.duration ?? 0, 3);
  }

  const label = eng.last_choice ? (NICE[eng.last_choice] || eng.last_choice) : "—";
  el("nowplaying").innerHTML = `now playing <b>${label}</b>${eng.song ? ` · ${eng.song}` : ""}`;
  if (eng.last_choice && eng.last_choice !== lastChoice) {
    lastChoice = eng.last_choice;
    const oct = g && g.vertical > 0.6 ? '<span class="oct">⬆ octave up</span>'
      : (g && g.vertical < -0.6 ? '<span class="oct">⬇ octave down</span>' : "");
    el("what").innerHTML = label + oct;
    flash(el("wandcard")); flash(el("what"));
  }
}
function flash(node) {
  node.classList.add("live");
  clearTimeout(node._t); node._t = setTimeout(() => node.classList.remove("live"), 1400);
}

// wand card text tracks the roster wand
function wandText(connected, variant) {
  el("wandst").textContent = connected ? "connected" : "not connected";
  el("wandsub").textContent = connected
    ? (variant === "cv" ? "webcam hand — pinch to grab" : variant === "sim" ? "phone motion — hold to grab" : "hardware wand")
    : "enable the camera, or scan to conduct";
}

// ── left: score lanes (one mini piano roll per instrument) ───────────────────
let laneSig = "";
function renderLanes(tracks) {
  const playable = tracks.filter((t) => t.roll).slice(0, 12);
  el("leftempty").hidden = playable.length > 0;
  const sig = playable.map((t) => t.name + ":" + t.note_count).join("|");
  if (sig === laneSig) return;                 // only rebuild when the song changes
  laneSig = sig;
  const host = el("lanes");
  host.innerHTML = "";
  const bars = Math.max(1, ...playable.map((t) => (t.roll.length ? Math.max(...t.roll.map((r) => r[0])) + 1 : 1)));
  playable.forEach((t) => {
    const lane = document.createElement("div");
    lane.className = "lane" + (t.is_melody ? " melody" : "");
    lane.innerHTML = `<div class="lbl"><span>${t.instrument || t.name}</span><span class="n">${t.note_count}</span></div><canvas></canvas>`;
    host.appendChild(lane);
    drawLane(lane.querySelector("canvas"), t, bars);
  });
}
function drawLane(canvas, track, bars) {
  const dpr = window.devicePixelRatio || 1;
  const W = (canvas.width = canvas.clientWidth * dpr);
  const H = (canvas.height = 34 * dpr);
  const ctx = canvas.getContext("2d");
  const total = bars * 16;
  const LO = 36, HI = 84;
  const col = track.is_drum ? "#8a8378" : (track.is_melody ? "#ffe3a3" : "#e7c583");
  ctx.fillStyle = col;
  for (const [b, on, dur, pitch] of track.roll) {
    const x = ((b * 16 + on) / total) * W;
    const w = Math.max(1.2 * dpr, (dur / total) * W);
    const y = H - ((Math.max(LO, Math.min(HI, pitch)) - LO) / (HI - LO)) * (H - 4 * dpr) - 2 * dpr;
    ctx.fillRect(x, y - 1.4 * dpr, w, 2.8 * dpr);
  }
}
window.addEventListener("resize", () => { laneSig = ""; });   // force lane redraw at new width

// ── bottom: live scrolling piano roll ────────────────────────────────────────
const WINDOW_MS = 4200, FUTURE_MS = 1500, RLO = 36, RHI = 96;
function drawRoll() {
  const canvas = el("rollcanvas");
  const dpr = window.devicePixelRatio || 1;
  const W = (canvas.width = canvas.clientWidth * dpr);
  const H = (canvas.height = canvas.clientHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, W, H);
  const now = clock && clock.theta !== null ? clock.serverNow() : null;
  if (now === null) { requestAnimationFrame(drawRoll); return; }
  const pxPerMs = W / WINDOW_MS;
  const headX = W - FUTURE_MS * pxPerMs;
  ctx.strokeStyle = "rgba(255,227,163,.5)"; ctx.lineWidth = 1.5 * dpr;
  ctx.beginPath(); ctx.moveTo(headX, 0); ctx.lineTo(headX, H); ctx.stroke();
  for (let i = notes.length - 1; i >= 0; i--) {
    const n = notes[i];
    const x = W - (now + FUTURE_MS - n.at) * pxPerMs;
    const w = Math.max(3 * dpr, n.dur * pxPerMs);
    if (x + w < 0) { notes.splice(i, 1); continue; }
    if (x > W) continue;
    const y = H - ((Math.max(RLO, Math.min(RHI, n.pitch)) - RLO) / (RHI - RLO)) * (H - 8 * dpr) - 4 * dpr;
    ctx.globalAlpha = n.at <= now ? 0.95 : 0.4;
    ctx.fillStyle = n.color;
    ctx.fillRect(x, y - 3 * dpr, w, 6 * dpr);
  }
  ctx.globalAlpha = 1;
  requestAnimationFrame(drawRoll);
}

function ingest(e) {
  if (seen.has(e.id)) return;
  seen.add(e.id);
  if (seen.size > 4000) seen.clear();
  notes.push({ at: e.at, dur: e.dur || 200, pitch: noteToMidi(e.note), color: colorFor(e.section, e.art === "drum") });
  // pulse the phone at note time (on the synced clock)
  const delay = clock && clock.theta !== null ? Math.max(0, Math.min(1500, e.at - clock.serverNow())) : 0;
  setTimeout(() => pulse(e.section), delay);
}

// ── audio (this screen is the orchestra when no phone has joined) ─────────────
async function ensureAudio() {
  if (audioReady) return;
  try { await synth.unlock(); clock.attachAudio(synth.ctx); audioReady = true; }
  catch (err) { console.warn("[console] audio unlock failed", err); }
}

// ── wire up ──────────────────────────────────────────────────────────────────
conn = new Conn({ role: "stage", session, key: "console" });
clock = new Clock((o) => conn.send(o));
synth = new Synth(clock, null);

conn.on(P.CLOCK_PONG, (m) => clock.handlePong(m));
conn.on(P.ROSTER, renderRoster);
conn.on(P.ENGINE_STATE, applyEngine);
conn.on(P.SCHED_NOTES, (m) => {
  for (const e of m.events) {
    ingest(e);
    if (started && readySections === 0 && e.section === P.SECTION_ALL) synth.schedule(e);
  }
});
conn.on(P.SCHED_CANCEL, (m) => { if (m.allnotesoff) synth.panic(); });

conn.onOpen((welcome) => {
  const cfg = welcome.config || {};
  const join = cfg.wand_url || cfg.join_url;
  if (join && window.qrcode) {
    const qr = window.qrcode(0, "M"); qr.addData(join); qr.make();
    el("qr").innerHTML = qr.createSvgTag({ cellSize: 5, margin: 1, scalable: true });
  }
});

// transport
el("start").addEventListener("click", async () => {
  await ensureAudio();
  started = true;
  conn.send({ t: P.ADMIN_CMD, cmd: "start" });
});
el("stop").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "stop" }));
el("panic").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "allnotesoff" }));
el("tempo").addEventListener("input", (e) => {
  el("bpm").textContent = e.target.value;
  conn.send({ t: P.ADMIN_CMD, cmd: "tempo", args: { bpm: +e.target.value } });
});

// camera wand — load the iframe only when asked (MediaPipe is heavy)
el("camstart").addEventListener("click", async () => {
  if (!camStarted) { el("camframe").src = `../cvwand/?s=${encodeURIComponent(session)}`; camStarted = true; }
  el("camstart").hidden = true;
  await ensureAudio();
  if (!started) { started = true; conn.send({ t: P.ADMIN_CMD, cmd: "start" }); }
});

// join QR popover
el("joinbtn").addEventListener("click", () => { el("qrpop").hidden = !el("qrpop").hidden; });

conn.connect();
clock.start();                 // begin pinging immediately so the roll has a clock
requestAnimationFrame(drawRoll);
