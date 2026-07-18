# Audience audio-sync research — how others do it (2026-07-18)

Research into how existing systems sync audio across many phones for large
audiences, to sanity-check and improve our clock-sync. **Bottom line: our design
is essentially a simplified version of IRCAM's Soundworks — the validated,
mainstream pattern. The one real gap is clock-drift compensation.**

## The reference implementation: IRCAM `@ircam/sync` / Soundworks

Lambert, Robaszkiewicz & Schnell, *"Synchronisation for Distributed Audio
Rendering over Heterogeneous Devices, in HTML5"* (Web Audio Conference 2016).
- Repo: https://github.com/ircam-ismm/sync · npm `@ircam/sync` (MIT)
- Soundworks plugin: https://soundworks.dev/plugins/sync.html
- Paper: https://hal.science/hal-01304889

Their algorithm, vs what we already do:

| Technique | Soundworks | Us (clock.js) |
|---|---|---|
| Ping **series** (burst), not single pings | 10 pings/series, 0.25s apart, then 10–20s between series | ✅ burst of 10 @150ms, then 1/2s |
| **Minimum-RTT** filtering | keeps shortest-RTT sample | ✅ we pick min-RTT sample |
| Broadcast one shared-clock cue, convert locally | yes | ✅ "play at server-time T", client maps to audio time |
| Look-ahead scheduling | ~100ms ahead, 25ms tick (Chris Wilson "Two Clocks") | ✅ 150–600ms lookahead |
| Map to **AudioContext.currentTime** | uses ctx clock as the local clock | ⚠️ we hop performance.now()→ctx (works, one extra hop) |
| **Clock-rate / drift estimation** | fits `serverTime ≈ offset + rate·localTime` via regression; compensates crystal drift | ❌ **we estimate offset only — this is the gap** |
| Monotonic + rate-limited updates | clamps adaptation (~160 PPM) so corrections are inaudible | ⚠️ we ignore <2ms, snap >50ms; no rate model |

**Measured accuracy they report: ~1–10 ms (≈5 ms SD) across heterogeneous phones**
— "more accurate than the audio block duration." That's our target too.

## The "Waterloo symposium" (medium confidence)

Most likely the **University of Waterloo Games Institute "Android Streamed Audio
Experiment"** by **Karen Collins** (Canada Research Chair in Interactive Audio):
streamed different instrument tracks of one song from a laptop over WiFi to
multiple phones, each phone playing its own part, **instrument switchable
mid-stream** — a near-exact match for our "each phone is an instrument" idea.
- https://uwaterloo.ca/games-institute/audio-experiment
- Caveat: no page confirms a "symposium," sync algorithm, device count, or latency
  numbers. If the reference was about the sync *technique*, the IRCAM WAC work above
  is the more likely source. **Confirm with the user.**

## Other systems (scale + method)

| System | Sync method | Scale |
|---|---|---|
| Soundworks / @ircam/sync | ping-series + offset+drift regression → AudioContext | hundreds, per-phone playback |
| Crowd in C[loud] (Sang Won Lee) | cloud service; sound generated on each phone | audience-scale |
| massMobile (Georgia Tech) | phones *send* control; sound from central PA | large shows (not per-phone) |
| Open Symphony (Queen Mary) | web voting/conducting; audio from performers | ~120 participants |
| Poème Numérique | **ultrasound triggers (18–20.7kHz)**, no network sync | ~250 in a hall |
| Stanford MoPhO / SLOrk | performer ensemble, OSC over LAN | tens |
| **Ableton Link** | P2P UDP **multicast** on LAN, tempo+phase | many, **LAN-only** (can't route WAN) |

Note two devices physically adjacent phase-lock audibly only within ~2–3ms;
**per-device output latency (hundreds of ms, largely un-queryable) is usually the
dominant error, not clock offset** — which is why we have the manual trim slider.

## Recommended upgrades (priority order)

1. **Add clock-drift (rate) estimation** — the #1 correctness win for anything
   longer than ~1 minute. Fit `serverMs ≈ offset + rate·perfNow` by linear
   regression over recent best-ping samples instead of tracking offset only.
   Without it, cheap phone crystals (tens–hundreds of PPM) slide audibly over a
   multi-minute set. *This is the main thing we're missing.*
2. Make theta updates monotonic + rate-limited (clamp ~a few hundred PPM) so a
   re-estimate never causes an audible jump.
3. Consider keying the sync clock directly to `AudioContext.currentTime` (drop the
   performance.now()→ctx hop).
4. Keep the per-device latency trim; consider an auto-calibration step.
5. `@ircam/sync` is MIT and drop-in if we'd rather adopt than maintain our own.

## What we're already doing right

Ping-series + min-RTT filtering, single broadcast cue with local conversion,
conservative 150–600ms lookahead, audio-unlock-before-sync, and a manual latency
trim. That's the validated core. The gap is drift compensation (#1 above).
