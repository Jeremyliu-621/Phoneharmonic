// "Start Here" — a live status dashboard + guided test. Connects for roster/engine
// status only (no audio) and turns the lights green as each part comes online.

import { Conn } from "../shared/ws.js";
import * as P from "../shared/protocol.js";

const params = new URLSearchParams(location.search);
const session = params.get("s") || "lol1";
const el = (id) => document.getElementById(id);

const conn = new Conn({ role: "stage", session });

function setTile(id, on, val) {
  el("t-" + id).classList.toggle("on", on);
  el("t-" + id).classList.toggle("off", !on);
  if (val !== undefined) el("v-" + id).textContent = val;
}

conn.onOpen(() => { el("d-server").classList.add("ok"); el("t-server").classList.add("on"); });
conn.onClose(() => { el("d-server").classList.remove("ok"); el("t-server").classList.remove("on"); el("t-server").classList.add("off"); });

conn.on(P.ROSTER, (m) => {
  const eng = m.engine || {};
  const w = m.wand || {};
  const ready = m.sections.filter((s) => s.connected && s.ready).length;
  const playing = !!eng.playing;

  setTile("play", playing, playing ? "▶ playing" : "idle");
  setTile("wand", !!w.connected, w.connected ? w.variant : "none");
  setTile("phones", ready > 0, String(ready));

  const thetas = m.sections.filter((s) => s.connected && s.theta != null).map((s) => s.theta);
  const spread = thetas.length >= 2 ? (Math.max(...thetas) - Math.min(...thetas)) : null;
  setTile("sync", spread == null || spread <= 30, spread == null ? (ready ? "…" : "solo") : spread.toFixed(0) + "ms");

  // step checks
  const cPlay = el("c-play");
  cPlay.textContent = playing ? "🟢 orchestra is playing" : "⚪ waiting — orchestra is idle";
  cPlay.classList.toggle("done", playing);

  const cWand = el("c-wand");
  cWand.textContent = w.connected ? `🟢 ${w.variant} wand connected — move it!` : "⚪ waiting — no wand connected yet";
  cWand.classList.toggle("done", !!w.connected);

  const cPh = el("c-phones");
  cPh.textContent = ready > 0 ? `🟢 ${ready} phone${ready > 1 ? "s" : ""} joined` : "⚪ 0 phones joined — this is optional";
  cPh.classList.toggle("done", ready > 0);

  const NICE = { lower_imitation: "Lower imitation", contrary_motion: "Contrary motion", sustained: "Sustained chord",
    delayed: "Delayed echo", rhythmic_dense: "Rhythmic (busy)", rest: "Rest (silence)" };
  el("nowplaying").textContent = eng.last_choice ? (NICE[eng.last_choice] || eng.last_choice) : "—";
});

el("startbtn").addEventListener("click", () => conn.send({ t: P.ADMIN_CMD, cmd: "start" }));

conn.connect();
