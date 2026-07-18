// Editor / control room. Manual control of the whole system with no wand and no
// ML: start/stop, tempo, force which accompaniment plays, and assign an
// instrument to each phone. Also monitors audio so you can hear it on one laptop.

import { Conn } from "../shared/ws.js";
import { Clock } from "../shared/clock.js";
import { Synth } from "../shared/synth.js";
import * as P from "../shared/protocol.js";

const params = new URLSearchParams(location.search);
const session = params.get("s") || "lol1";
const el = (id) => document.getElementById(id);

const INSTRUMENTS = ["violin", "viola", "cello", "flute", "clarinet", "piano", "bass", "synth", "bell"];
const NICE = {
  auto: "Auto (ranker)", lower_imitation: "Lower imitation", contrary_motion: "Contrary motion",
  sustained: "Sustained chord", delayed: "Delayed echo", rhythmic_dense: "Rhythmic (busy)", rest: "Rest (silence)",
};

let started = false;
let readySections = 0;
let forced = "auto";
let barBars = [];

const conn = new Conn({ role: "stage", session });
const clock = new Clock((obj) => conn.send(obj));
const synth = new Synth(clock, () => pulseBars());

// --- bar activity meter ---
for (let i = 0; i < 16; i++) { const b = document.createElement("div"); b.className = "b"; el("bars").appendChild(b); barBars.push(b); }
let barIdx = 0;
function pulseBars() {
  const b = barBars[barIdx % barBars.length];
  b.style.height = "26px";
  setTimeout(() => { b.style.height = "4px"; }, 180);
  barIdx++;
}

// --- candidate override buttons ---
function renderCandidates(list) {
  if (el("candidates").children.length) return;   // build once
  const all = ["auto", ...list];
  for (const c of all) {
    const btn = document.createElement("button");
    btn.textContent = NICE[c] || c;
    btn.dataset.cand = c;
    btn.className = c === "auto" ? "active" : "";
    btn.addEventListener("click", () => {
      forced = c;
      conn.send({ t: P.ADMIN_CMD, cmd: "force", args: { candidate: c } });
      [...el("candidates").children].forEach((x) => x.classList.toggle("active", x.dataset.cand === c));
    });
    el("candidates").appendChild(btn);
  }
}

// --- roster / engine status ---
conn.on(P.CLOCK_PONG, (m) => clock.handlePong(m));
conn.on(P.SCHED_NOTES, (m) => {
  if (!started || readySections > 0) return;   // monitor only when laptop is the orchestra
  for (const e of m.events) if (e.section === P.SECTION_ALL) synth.schedule(e);
});
conn.on(P.SCHED_CANCEL, (m) => { if (m.allnotesoff) synth.panic(); });
conn.on(P.ROSTER, (m) => {
  readySections = m.sections.filter((s) => s.connected && s.ready).length;
  const eng = m.engine || {};
  if (eng.candidates) renderCandidates(eng.candidates);
  renderSong(eng);
  el("nowplaying").textContent = eng.last_choice ? (NICE[eng.last_choice] || eng.last_choice) : "—";
  if (eng.bpm && !tempoDragging) { el("tempo").value = eng.bpm; el("tempoval").textContent = eng.bpm + " BPM"; }

  // wand + gesture
  const w = m.wand || {};
  el("wanddot").classList.toggle("ok", !!w.connected);
  el("wandstate").textContent = w.connected ? w.variant : "none";
  const g = eng.gesture;
  for (const k of ["energy", "size", "vertical", "rotation"]) {
    el("g_" + k).textContent = g ? g[k].toFixed(2) : "—";
  }

  // sections table
  if (m.sections.length === 0) {
    el("rows").innerHTML = `<tr><td colspan="5" class="muted">no phones yet — the laptop plays everything. Scan the stage QR or open a section page to add instruments.</td></tr>`;
  } else {
    el("rows").innerHTML = m.sections.map((s) => `<tr>
      <td><span class="dot ${s.connected ? "ok" : ""}"></span></td>
      <td>${s.id}</td>
      <td>${instrumentSelect(s.id, s.instrument)}</td>
      <td>${s.ready ? "✓" : "—"}</td>
      <td>${s.theta == null ? "—" : s.theta.toFixed(1) + "ms"}</td></tr>`).join("");
    bindSelects();
  }
});

function instrumentSelect(sid, current) {
  const opts = INSTRUMENTS.map((i) => `<option value="${i}" ${i === current ? "selected" : ""}>${i}</option>`).join("");
  return `<select data-sid="${sid}">${opts}</select>`;
}
function bindSelects() {
  el("rows").querySelectorAll("select").forEach((sel) => {
    sel.addEventListener("change", () => {
      conn.send({ t: P.STAGE_ASSIGN, section_id: sel.dataset.sid, instrument: sel.value });
    });
  });
}

// --- song info + MIDI drop ---
function renderSong(eng) {
  if (!eng || !eng.song) return;
  el("songname").textContent = eng.song;
  const KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  el("songmeta").textContent = `${KEYS[eng.key_root] || "?"} major · ${eng.bpm} BPM · ${eng.bars} bars`;
  const tracks = eng.tracks || [];
  if (!tracks.length) return;
  el("tracks").innerHTML = tracks.map((t) => `<tr>
    <td>${t.is_melody ? '<span class="tag">melody</span>' : (t.is_drum ? "🥁" : "")}</td>
    <td>${t.name}</td><td>${t.instrument}</td><td>${t.note_count}</td></tr>`).join("");
}

function abToBase64(ab) {
  const bytes = new Uint8Array(ab);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
async function uploadMidi(file) {
  if (!file) return;
  el("drop").textContent = `reading ${file.name}…`;
  const ab = await file.arrayBuffer();
  conn.send({ t: P.SONG_LOAD, name: file.name, data: abToBase64(ab) });
  el("drop").textContent = `⬇ Drop a .mid file here, or click to choose one`;
}
const drop = el("drop");
drop.addEventListener("click", () => el("midifile").click());
el("midifile").addEventListener("change", (e) => uploadMidi(e.target.files[0]));
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => uploadMidi(e.dataTransfer.files[0]));
conn.on(P.ERR, (m) => { if (m.code === "bad_midi") { el("drop").textContent = `⚠ ${m.msg} — try another file`; } });

conn.onOpen((w) => { el("status").textContent = `connected · session ${w.config.session}`; });
conn.onClose(() => { el("status").textContent = "reconnecting…"; });

// --- transport ---
el("enable").addEventListener("click", async () => {
  if (!started) {
    await synth.unlock();
    clock.attachAudio(synth.ctx);
    clock.start();
    started = true;
    el("enable").textContent = "▶ Restart";
  }
  conn.send({ t: P.ADMIN_CMD, cmd: "start" });
});
el("stop").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "stop" }));
el("panic").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "allnotesoff" }));

let tempoDragging = false;
el("tempo").addEventListener("input", (e) => {
  tempoDragging = true;
  el("tempoval").textContent = e.target.value + " BPM";
  conn.send({ t: P.ADMIN_CMD, cmd: "tempo", args: { bpm: parseInt(e.target.value, 10) } });
});
el("tempo").addEventListener("change", () => { tempoDragging = false; });

conn.connect();
