// Clock sync — the #1 technical risk lives here.
//
// Estimates theta = (server monotonic ms) - (performance.now() ms) using an
// NTP-style ping burst, then keeps it fresh with periodic pings. Also maps a
// server time to this device's AudioContext time so scheduled notes fire in
// sample-accurate agreement across devices.
//
// Timebases:
//   server : server_time_ms()      (monotonic, from the server)
//   client : performance.now()      (monotonic, this tab)
//   audio  : ctx.currentTime * 1000 (this device's audio hardware clock)

import { CLOCK_PING, CLOCK_PONG } from "./protocol.js";

const BURST_COUNT = 10;
const BURST_SPACING_MS = 150;
const PERIODIC_MS = 2000;
const WINDOW = 15;           // sliding window of recent samples
const IGNORE_MS = 2;         // |delta theta| below this: leave theta alone
const SNAP_MS = 50;          // above this: snap + signal a resync

const A2P_SAMPLES = 5;       // median window for the performance->audio anchor

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export class Clock {
  constructor(send) {
    this._send = send;              // (obj) => void
    this._pending = new Map();      // ping id -> t0
    this._samples = [];             // {offset, rtt}
    this._nextId = 1;
    this.theta = null;              // ms; null until first pong
    this.rtt = null;
    this._ctx = null;
    this._a2p = null;               // ms: performance.now() - ctx.currentTime*1000
    this._a2pSamples = [];
    this.trimSec = 0;               // per-device output-latency compensation
    this.onResync = null;           // callback(deltaMs) on a >SNAP_MS jump
    this._timers = [];
  }

  start() {
    for (let i = 0; i < BURST_COUNT; i++) {
      this._timers.push(setTimeout(() => this._ping(), i * BURST_SPACING_MS));
    }
    this._periodic = setInterval(() => this._ping(), PERIODIC_MS);
  }

  stop() {
    this._timers.forEach(clearTimeout);
    clearInterval(this._periodic);
    if (this._a2pTimer) clearInterval(this._a2pTimer);
  }

  _ping() {
    const id = this._nextId++;
    const t0 = performance.now();
    this._pending.set(id, t0);
    this._send({ t: CLOCK_PING, id, t0 });
  }

  // Called by the ws layer for every clock.pong.
  handlePong(msg) {
    if (msg.t !== CLOCK_PONG) return;
    const t0 = this._pending.get(msg.id);
    if (t0 === undefined) return;
    this._pending.delete(msg.id);
    const t1 = performance.now();
    const rtt = t1 - t0;
    const offset = msg.ts - (t0 + t1) / 2;   // server - client midpoint
    this._samples.push({ offset, rtt });
    if (this._samples.length > WINDOW) this._samples.shift();
    this._recompute();
  }

  _recompute() {
    // Best-of-N: trust the sample with the least round-trip (least queueing).
    let best = this._samples[0];
    for (const s of this._samples) if (s.rtt < best.rtt) best = s;
    this.rtt = best.rtt;
    const newTheta = best.offset;

    if (this.theta === null) {
      this.theta = newTheta;
      return;
    }
    const delta = newTheta - this.theta;
    if (Math.abs(delta) < IGNORE_MS) return;
    this.theta = newTheta;
    if (Math.abs(delta) > SNAP_MS && this.onResync) this.onResync(delta);
  }

  // Server monotonic ms, estimated on this device's clock right now.
  serverNow() {
    return performance.now() + (this.theta ?? 0);
  }

  // --- audio mapping ---
  attachAudio(ctx) {
    this._ctx = ctx;
    this._sampleA2P();
    this._a2pTimer = setInterval(() => this._sampleA2P(), 1000);
  }

  _sampleA2P() {
    if (!this._ctx) return;
    const p0 = performance.now();
    const c = this._ctx.currentTime * 1000;
    const p1 = performance.now();
    const sample = (p0 + p1) / 2 - c;
    this._a2pSamples.push(sample);
    if (this._a2pSamples.length > A2P_SAMPLES) this._a2pSamples.shift();
    this._a2p = median(this._a2pSamples);
  }

  // Map a server time (ms) to this AudioContext's time (seconds) for scheduling.
  serverToAudioTime(serverMs) {
    if (this.theta === null || this._a2p === null) return null;
    const clientPerf = serverMs - this.theta;          // performance.now() ms at that instant
    return (clientPerf - this._a2p) / 1000 - this.trimSec;
  }

  ready() {
    return this.theta !== null && this._a2p !== null;
  }
}
