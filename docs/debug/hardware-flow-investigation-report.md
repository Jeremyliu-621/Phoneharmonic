# Phoneharmonic hardware-flow investigation report

**Date:** 2026-07-19 (America/Toronto)  
**Checkout:** commit `85a94a7434a70f26a9ecf4593d3cd7556914c0c3`, branch `firmware` (`origin/firmware`)  
**Machine:** Apple ARM64 Mac, macOS 26.2 (build 25C56), Python 3.14, Node v26.2.0  
**Network observed:** `en0` active at `192.168.18.6/24`; this was an ordinary `192.168.18.0/24` LAN, not the intended phone hotspot. `networksetup` reported no associated AirPort network, while `ifconfig` and HTTP reachability confirmed the active address.  
**Physical hardware actually exercised:** none. No UNO Q serial device was present (only Bluetooth/debug pseudo-terminals), no reachable board hostname was supplied/discovered, no phones were available to operate, and no phone-hotspot provider/device was available. Hardware, phone-audio, camera-gesture, LED/buzzer, and hotspot claims are therefore explicitly `BLOCKED`, not inferred from simulation.

## Executive summary

**Overall verdict: NOT READY for the hardware demo.** The current checkout has a credible protocol and deterministic fallback, but the required physical acceptance run was unavailable and several current-code failures would affect the intended performance:

1. The correct combined route is the standalone `cv_hand_movements` page as `admin` plus the UNO Q as the sole `wand`. The embedded `web/cvwand/` client is a competing wand client and is not the correct left-hand controller for the combined hardware demo ([standalone connection](../../cv_hand_movements/net/conn.js#L1-L25), [hardware-slot priority](../../server/main.py#L298-L318)).
2. “Select mode” is not a server mode. One finger changes only local CV state and emits no selection message; hardware aim runs continuously in every mode. Selection is consequently neither entered nor latched by the one-finger pose ([emitter](../../cv_hand_movements/net/emit.js#L11-L24), [continuous aim](../../server/main.py#L790-L825)).
3. Hardware shake-to-select-all is implemented server-side, not just in the webcam route. A two-section protocol run reproduced `wand shake -> select all`, `wand.state.aim_section: null`, `wand.cmd.aim: null`, and a deterministic `fx.expr` targeted to `section: "all"`. However, “all” lasts only 1.5 seconds and then continuous pointing resumes, so it does not satisfy durable selection preservation ([latch](../../server/main.py#L58-L60), [shake path](../../server/main.py#L790-L805)).
4. The intended standalone left-hand route contradicts the “pinch disabled” requirement: it still scrubs locally and emits `admin.cmd rewind|forward`. It also tests pinch before MediaPipe's `Closed_Fist`; a constructed closed-fist result with close thumb/index classified as `PINCH`, so pinch can prevent pause ([classification](../../cv_hand_movements/cv/gestures.js#L67-L95), [wire emit](../../cv_hand_movements/main.js#L135-L152)). The embedded webcam route contains the desired fist-first and disabled-pinch logic, but using it would contend for the wand slot ([embedded logic](../../web/cvwand/cvwand.js#L203-L238)).
5. A current-checkout isolated live server sent real decision-model and bar-model requests, but both failed immediately as `URLError`; a direct diagnostic proved the exact Python error was `CERTIFICATE_VERIFY_FAILED`. System `curl` with the same configured endpoints/auth returned HTTP 200 (decision calls in 3.858 s and 2.677 s; bar call in 3.006 s), proving endpoint/auth reachability but not application consumption. The decision calls also exceeded the configured 2,000 ms budget. Runtime therefore used `decision_source: heuristic`, and no generated bar was consumed.
6. A clean no-cache start loaded the hardcoded `loop-CGAmF`, because `WM_DEFAULT_SONG=zelda-fairy.mid` points into an empty `songs/` directory. A cached MIDI did take precedence in a separate isolated start. Playback remained usable without a wand at protocol level.
7. Two additional boundary defects were reproduced: the first recognized stroke after a wand connection can be applied before the newly calculated aim (and can inherit a stale disconnected aim), and reconnecting with the same hardware `client_id` resets `det` mode to `ai`.
8. The local TLS certificate is self-signed, not trusted by the local system, and is valid only for `192.168.18.6`, `localhost`, and `127.0.0.1`. A hotspot IP change will create both trust and hostname/SAN failures unless certificates/routes are prepared again.

Protocol-level and unit-test results are useful evidence, but none are represented as proof that the physical UNO Q, phone audio, visible phone UI, or hotspot works.

## Requirement checklist

Status meanings: `PASS` = directly verified at the requirement's scope; `PARTIAL` = some hops verified but physical/visible/audible scope remains; `FAIL` = current behavior contradicts the requirement; `BLOCKED` = required dependency was unavailable.

| Requirement | Status | Strongest evidence |
|---|---|---|
| Correct combined route identified | PASS | Standalone CV hello is `role: admin`; UNO Q contract is `role: wand`; hardware keeps the slot over camera roles. |
| Physical left hand enters Select with one finger | FAIL | One finger sets local `SELECT`, but emits no wire/server selection mode. Camera itself was also unavailable for physical confirmation. |
| Physical UNO Q pointing selects one phone | BLOCKED | Protocol-equivalent `wand.imu` resolved yaw `-60.0°` to `s2`; no physical board/phone was available. |
| Selection observable in telemetry | PASS | Isolated runtime emitted `wand.state {aim_section:"s2", yaw_deg:-60.0}` and roster `engine.aimed:"s2"`. |
| Selected phone visibly indicated | PARTIAL | Console code maps `engine.aimed` to `.card.aimed` glow; in-app browser was unavailable and no phone/UI was observed. |
| Physical shake selects all | BLOCKED | Server implementation and protocol-equivalent IMU passed; no physical shake was performed. |
| Hardware shake hop exists | PASS | `ShakeDetector` recognized four high-g peaks and server emitted null aim plus all-target expression. |
| Individual selection survives DET/AI mode change | PARTIAL | Protocol runtime retained `s2` across both mode messages while orientation was unchanged; no physical gesture/UI/audio. |
| Select-all survives subsequent mode/use | FAIL | It is a 1,500 ms latch, not durable selected state; subsequent IMU after expiry re-aims an individual phone. |
| Edit affects only selected section | PARTIAL | DET runtime emitted `fx.expr {section:"s2", semis:12}`; browser/phone audible result blocked. |
| Select-all edit affects all sections | PARTIAL | DET runtime emitted `fx.expr {section:"all", semis:12}` during latch; physical/audible result blocked. |
| Selection does not mute/stop unselected instruments | PARTIAL | Two-section runtime scheduled events for both `s2` and `s3`; conductor no longer cancels on aim. No real phone audio. |
| Closed left fist pauses | BLOCKED | The downstream `admin.cmd stop` path passed, but physical recognition was unavailable and current classifier has a proven pinch-precedence defect. |
| Open left palm resumes | BLOCKED | Downstream `admin.cmd start` passed; no physical palm/camera run. |
| Pause is transport, not mute/gain/audio suspension | PASS | Server flips `session.playing`/engine transport false and emits global `sched.cancel allnotesoff`; no section mute/volume is changed. |
| Resume continues musical position | PASS | Isolated runtime resumed with an implied preserved offset of 51 bars, not bar zero; `_next_bar_idx` is deliberately retained. |
| Physical right hand ignored | PARTIAL | Unit selection chose only the strongest `Left` result and rejected a right-only result; no live camera trial. |
| Pinch rewind/forward disabled | FAIL | Standalone route emits rewind/forward on pinch release and local router continuously scrubs. |
| Pinch cannot swallow fist | FAIL | Constructed `Closed_Fist` + close thumb/index returned `{"gesture":"PINCH"}` because pinch is checked first. |
| Console, phones, server, Arduino agree after pause/resume | BLOCKED | Protocol state and `wand.cmd.playing` passed; console audio, two phones, and board LED were unavailable. |
| Clean no-hardware song identified | PASS | Isolated no-cache boot reported `loop-CGAmF`; configured default file was absent. |
| Claimed hardcoded/deterministic fallback accurate by default | PASS | Under this checkout and empty `songs/`, yes: the built-in deterministic four-bar loop is the final fallback. |
| Playback usable without wand | PARTIAL | `smoke_test.py` received valid scheduled music without hardware; audible browser output was not exercised. |
| Connect/disconnect does not change song/transport | PARTIAL | Protocol reconnect kept `loop-CGAmF` and `playing:true`; no physical network/power cycle. |
| Connect/disconnect does not change decision/mode unexpectedly | FAIL | Same-client reconnect changed `wand.cmd.mode` from `det` to `ai`; stale aim also survived until new IMU. |
| Laptop hotspot IP discovered | BLOCKED | No hotspot was active; observed address was ordinary-LAN `192.168.18.6`. |
| UNO Q stable on hotspot | BLOCKED | No board or hotspot. |
| At least two real phones on hotspot | BLOCKED | No phones or hotspot. |
| Correct HTTP/WS and HTTPS/WSS hotspot routes | BLOCKED | Routes traced statically; dynamic hotspot reachability not tested, and current certificate would not match a new IP. |
| Certificate/camera/firewall/client isolation okay on hotspot | BLOCKED | Certificate is currently untrusted and IP-bound; other conditions unavailable. |
| Selection/transport/DET/AI work on hotspot | BLOCKED | No hotspot hardware run. |
| Hotspot sync/stability acceptable | BLOCKED | No devices or latency capture. |
| Two-finger gesture sets server mode `det` | PARTIAL | Admin `wand.mode det` changed live roster while protocol hardware remained `variant:hw`; physical hand unavailable. |
| DET keeps physical wand/IMU active | BLOCKED | Protocol hardware client remained owner and streamed IMU; no physical UNO Q. |
| DET maps tilt directly, with no model request | PASS | Full positive `ay` produced scale-locked `+12` on `s2`; after mode switch, this path did not invoke `_model.request`. |
| DET targets selected/all correctly | PARTIAL | Both exact payloads observed; audible phones blocked and all target is transient. |
| Three-finger gesture sets server mode `ai` | PARTIAL | Admin `wand.mode ai` changed live roster; physical hand unavailable. |
| Physical AI gesture reaches conductor | BLOCKED | Optional hardware-protocol `wand.gesture sharp_up` reached `_gesture_in`; no physical IMU/ToF gesture. |
| Decision model called and distinguishable from fallback | FAIL | App called it, but Python TLS verification failed; bar decision remained `heuristic`. |
| Bar-line model called when needed | FAIL | App attempted calls, but each failed `URLError`; no generated line entered the cache. |
| Generated result accepted/scheduled/audible or traceable fallback | PARTIAL | Fallback was fully traceable to TLS error and heuristic/theory music continued; no generated consumption or physical audio. |
| AI selection scope correct | PARTIAL | Section-specific conductor state and heuristic event routing traced; select-all durability and physical audio remain deficient. |
| Caellum deployment/current provider identified | PASS | Caellum's documented deployment is merged bar-line v3 on Fireworks; current process instead uses Freesolo for both model clients. |
| Complete physical end-to-end route | BLOCKED | All implemented hops are traced below, but board, hands, phones, and hotspot were unavailable. |

## Exact run routes and commands

### Existing live process versus current checkout

An already-running process occupied `:8080/:8443`:

```text
PID 87901; started 2026-07-19 01:52:52 EDT
command: Python server/main.py
current commit timestamp: 2026-07-19 02:00:58 EDT
```

It was therefore older than the checkout under investigation. A read-only admin observation showed:

```json
{
  "playing": false,
  "sections": [],
  "wand": {"connected": true, "variant": "cv", "mode": "det"},
  "engine": {"song": "loop-CGAmF", "aimed": null,
             "decision_source": "heuristic", "last_choice": "sustained"}
}
```

That process was preserved. The current checkout was launched in isolation, with only persistence/log paths redirected to temporary locations:

```sh
env WM_HTTP_PORT=8180 WM_HTTPS_PORT=8543 \
  WM_SESSION_FILE=/private/tmp/phoneharmonic-investigation-session.json \
  WM_SONG_CACHE=/private/tmp/phoneharmonic-investigation-last-song \
  WM_SHOWS_DIR=/private/tmp/phoneharmonic-investigation-shows \
  WM_DISCOVERY_OFF=1 \
  .venv/bin/python server/main.py
```

Startup evidence:

```text
LAN IP detected: 192.168.18.6
HTTP/ws listening on :8180
HTTPS/wss listening on :8543
decision model: flash-1784391958-0aa455cc @ ...freesolo... (timeout 2000ms)
bar-line model: flash-1784407398-edf55491 @ ...freesolo... (timeout 7000ms)
```

Normal demo commands/URLs remain:

```sh
.venv/bin/python server/main.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory cv_hand_movements
```

- Console: `https://<current-laptop-IP>:8443/console/` after certificate trust, or `http://localhost:8080/console/` locally.
- Standalone left-hand CV: `http://127.0.0.1:8765/?ws=ws://<server-IP>:8080/ws` (use `localhost`/`127.0.0.1` on the laptop for camera secure-context eligibility).
- Phone section: `http://<server-IP>:8080/section/?s=lol1`.
- UNO Q: `ws://<server-IP>:8080/ws`, role `wand`.

The standalone CV app must be used as `admin`. Do not substitute `web/cvwand/`: it sends `wand.pose`/`wand.grab` as `wand-cv`, so although server hardware priority now prevents it from stealing an already-owned hardware slot, it is still the wrong input source and can become owner before/after hardware disconnect.

### TLS/route evidence

- Plain HTTP section route returned 200.
- Plain HTTP LAN console returned 302 to HTTPS when certs were present.
- HTTPS returned 200 only with verification disabled; normal verification failed.
- `security verify-cert` returned `CSSMERR_TP_NOT_TRUSTED`.
- Certificate subject/issuer are both `Phoneharmonic local development` (self-signed), valid 2026-07-19 to 2027-07-19, with SANs only `192.168.18.6`, `localhost`, and `127.0.0.1`.

## Automated tests

No application or test code was changed. Exact results:

| Command | Result |
|---|---|
| `.venv/bin/python -c "import websockets, mido; print('deps ok')"` | PASS, `deps ok`. |
| `.venv/bin/python server/tools/stream_probe_test.py` | PASS: 26 run, 25 pass, 1 skipped. Skip was IPv6 loopback bind unavailable in the initial managed sandbox; all other stream, telemetry, CV-state, URL, and launcher checks passed. |
| `node --test cv_hand_movements/tests/cv.test.mjs` | PASS: 9/9, 0 fail. Notably, the suite positively asserts pinch scrubbing; it does not test fist-versus-pinch classification. |
| `.venv/bin/python server/tests/test_strokes.py` | PASS: 8/8 synthetic stroke checks. |
| `.venv/bin/python server/tools/gesture_test.py` | PASS: 6/6 printed checks (baseline, big, twist, gentle, lift, pose). |
| `.venv/bin/python server/tools/policy_test.py` | PASS: 7/7 printed checks, including fake-model consumption and heuristic fallbacks. This validates logic against a localhost fake, not the configured remote service. |
| `.venv/bin/python server/tools/barmodel_test.py` | PARTIAL: checks 1–5 passed, including fake endpoint consumption; check 6 crashed because `freesolo/barline/dataset/train.jsonl` is absent. |
| `.venv/bin/python server/tools/midi_test.py` | PASS: 4/4 printed checks. |
| `.venv/bin/python server/tools/edit_test.py` | PASS: one end-to-end edit round-trip. |
| `.venv/bin/python server/tools/hum_test.py` | PASS: 4/4 printed checks. |
| `.venv/bin/python server/tools/rework_test.py` | FAIL immediately: it still expects aiming to solo/cancel unselected phones. That test is stale relative to the new explicit no-muting requirement and current conductor behavior ([obsolete assertion](../../server/tools/rework_test.py#L47-L59)). |
| `env WM_HTTPS_PORT=8498 .venv/bin/python server/tools/show_test.py` | PASS: 5/5 printed integration groups; alternate HTTPS port avoided collision with the preserved live server. |
| `env WM_HTTP_PORT=8180 .venv/bin/python server/tools/smoke_test.py` | PASS: 4/4 end-to-end groups; static files, section/clock, scheduled notes, and synthetic wand gesture. |

`pytest` was not installed in the project venv, so `test_strokes.py` was run using its documented direct runner. The missing bar dataset and stale rework assertion are repository-test hygiene failures; they were not repaired under this investigation-only goal.

## 1. Selection and edit targeting

### Intended route versus current behavior

The documentation describes one-finger Select followed by wand pointing. Current standalone CV does latch a local `SELECT` label, but `ServerEmitter.mode("SELECT")` intentionally sends nothing ([main state](../../cv_hand_movements/main.js#L159-L178), [wire map](../../cv_hand_movements/net/emit.js#L19-L50)). The server has only `ai` and `det` wand modes. It continuously integrates hardware `gz` and resolves aim on every IMU batch, regardless of the CV mode ([aimer](../../server/wandio.py#L90-L127), [update](../../server/main.py#L790-L825)).

Therefore:

- one finger does **not** arm or gate selection;
- pointing always changes `engine._aim`;
- selection is live orientation, not a durable selected section;
- mode changes preserve it only incidentally while the wand remains aimed;
- moving the wand for an AI gesture can also change target.

### Protocol runtime evidence (two simulated section sockets)

This used the production server and wire protocol with two section clients and a `role:wand` client; it was not physical proof.

```text
sections: s2 (violin), s3 (cello)
wand IMU: yaw -60.0° -> wand.state aim_section=s2
wand.mode det -> roster mode=det, variant=hw, engine.aimed=s2
positive ay tilt -> fx.expr {section:s2, semis:12, gain:1.0}
shake peaks -> "wand shake -> select all"
             wand.state aim_section=null; wand.cmd aim=null
positive ay during latch -> fx.expr {section:all, semis:12, gain:1.0}
wand.mode ai -> roster mode=ai, engine.aimed=s2 after re-aim
```

Both section sockets received the same scheduled batch containing destinations for `s2` and `s3`; each real phone filters to `all` or its own ID ([section filter](../../web/section/section.js#L115-L135)). The conductor no longer emits aim-time cancels, and arrangement rendering continues for all routed parts ([aim semantics](../../server/engine/conductor.py#L363-L370), [per-section rendering](../../server/engine/conductor.py#L599-L667)). Thus selection does not mute at the server boundary. Actual audible output remains `BLOCKED`.

The console's visible indication is implemented: roster `engine.aimed` maps to an instrument group and toggles `.card.aimed`, whose CSS adds a colored outline/glow ([console state](../../web/console/console.js#L297-L314), [card update](../../web/console/console.js#L135-L167), [CSS](../../web/console/index.html#L168-L171)). No browser surface was attached to this session, so visual behavior is `PARTIAL` rather than a visual pass.

### Shake-to-all boundary

The exact hardware hop exists:

```text
wand.imu -> ImuTelemetry -> WandAimer + ShakeDetector
         -> _select_all_until = now + 1500ms
         -> aim=None -> Conductor.on_aim(None)
         -> roster.engine.aimed=null + wand.state.aim_section=null + wand.cmd.aim=null
```

`ShakeDetector` uses four rising high-g impulses within 600 ms ([detector](../../server/wandio.py#L130-L175)). The missing hop is no longer recognition/protocol/server handling; it is **durable state**. After 1.5 s, the next batch resolves yaw to a section again. `Conductor.on_aim(None)` also clears all section-specific edit envelopes, making select-all an immediate state-folding action rather than a persistent target.

### Newly reproduced stale-aim/ordering defect

On a hardware-protocol connect, the initial `wand.cmd` carried stale aim `s1`, although `s1` had disconnected. The first IMU batch resolved the new aim to `s2`, but a stroke committed from that same batch logged `gesture(s1)` first. In `_update_aim`, `StrokeTracker.push()` and `engine.on_stroke()` run before the `if aim != self._last_aim: engine.on_aim(aim)` block ([ordering](../../server/main.py#L802-L817)). On disconnect, the server resets `session.wand` but does not clear `_last_aim` or `engine._aim` ([disconnect](../../server/main.py#L935-L961)).

This first failing boundary is server state/order, not recognition. It was observed once in the isolated run and is deterministic from the ordering; repeat coverage should be added.

## 2. Left-hand transport and disabled pinch

### Transport semantics

If the CV recognizer emits the intended commands, the downstream behavior is correct:

- `FIST` emits `admin.cmd stop`; `PALM` emits `admin.cmd start` ([standalone actions](../../cv_hand_movements/main.js#L159-L173)).
- Stop sets both `session.playing` and conductor `_playing` false and produces global all-notes-off; it does not change section mute, volume, or expression ([admin path](../../server/main.py#L583-L640), [engine transport](../../server/engine/conductor.py#L170-L203)).
- Start retains `_next_bar_idx` and recalculates timing anchor around that bar ([resume implementation](../../server/engine/conductor.py#L172-L186)).
- Runtime stop sent `sched.cancel {allnotesoff:true}` to both section clients. Runtime resume implied a preserved offset of 51 bars, proving it did not restart at bar zero.
- `wand.cmd.playing` mirrors state to the board; firmware makes play LED solid when playing and blink when paused ([server downlink](../../server/main.py#L775-L788), [firmware LED](../../firmware/uno_q/wand/sketch/sketch.ino#L42-L65)). Physical LED agreement is blocked.

The console has a distinct local audio-unlock gate: only its own Start button sets `started=true` and unlocks its synth ([console audio](../../web/console/console.js#L491-L518), [button](../../web/console/console.js#L554-L559)). A wand/CV start can make transport and roll visibly run without laptop audio. This is not a server mute and must be handled before judging transport by ear.

### Pinch requirement fails on the correct route

The correct standalone route currently:

- classifies pinch before built-in fist;
- pauses its local MIDI and scrubs continuously while pinched;
- resumes local playback after scrub;
- emits server `rewind`/`forward` on pinch release after horizontal travel.

The CV suite's ninth behavior check explicitly passes this current scrub behavior. A direct constructed classifier call using built-in `Closed_Fist` and close thumb/index returned:

```json
{"gesture":"PINCH","score":1}
```

Thus both “pinch disabled” and “pinch does not prevent fist” are `FAIL`. The desired implementation already exists only in `web/cvwand/`: it checks curled fingers before pinch and comments out scrub commands. That code cannot simply replace the standalone route because it joins as `wand-cv` and supplies its own wand poses.

Physical handedness remains unverified. Static/unit evidence shows `pickLeftHand` rejects all `Right` results and chooses the strongest `Left` result ([handedness](../../cv_hand_movements/cv/handedness.js#L10-L27)).

## 3. No-hardware fallback track

### Current precedence

The actual order is:

1. Construct hardcoded `builtin_song()` (`loop-CGAmF`) in `Conductor.__init__`.
2. Examine cached `.mid` and `.grid.json`; whichever exists with newest mtime wins.
3. If no cache exists, try `songs/$WM_DEFAULT_SONG` (`zelda-fairy.mid` by default/current env).
4. If the default path is absent, `_default_song()` returns silently, leaving the built-in loop.
5. If cache parsing fails, try the configured default; if that also raises, leave the built-in loop.

See [configuration](../../server/config.py#L77-L84), [restore precedence](../../server/main.py#L138-L200), and [built-in definition](../../server/engine/song.py#L51-L66).

Current repository evidence:

- no `server/data/last_song.mid` or `.grid.json` existed;
- `WM_DEFAULT_SONG` resolved to `zelda-fairy.mid`;
- `songs/` contained no files;
- clean isolated startup and roster reported `loop-CGAmF` (four bars, deterministic generators).

A separate isolated start copied the existing sample MIDI to a temporary cache base and reported:

```text
loaded song 'restored.mid': 7 bars, 2 parts
restored last song 'restored.mid'
```

This proves cache precedence. The claimed “completely deterministic/hardcoded fallback” is accurate **only because the configured default asset is missing**. It is not the intended flagship default described in comments/docs.

No-wand protocol playback passed: the smoke test received valid scheduled events. Connecting and disconnecting a hardware-protocol client left song and `playing` unchanged. However, reconnecting the same cached `client_id` changed downlink mode from `det` to `ai`:

```json
{
  "same_client_id": true,
  "before_disconnect": {"mode":"det"},
  "after_reconnect": {"mode":"ai"}
}
```

`_bind` creates a fresh default `WandSlot` on every owner connection, and disconnect does the same ([bind](../../server/main.py#L298-L318), [slot](../../server/session.py#L51-L64)).

## 4. Hotspot operation

**Overall: BLOCKED.** No phone hotspot, provider/device identity, board, or real phone clients were available. Ordinary LAN success is not treated as hotspot evidence.

Known current risks:

- Laptop address was `192.168.18.6`, not an iPhone-style `172.20.10.x` hotspot address.
- Previous repository evidence records that USB tether and Wi-Fi hotspot are isolated NAT contexts; laptop and UNO Q must join the same Wi-Fi side ([networking investigation](./networking-debugging.md#L26-L51)).
- The UNO Q app's container can see Docker gateway `172.19.0.1` instead of the LAN gateway; deployment must write current `wand_config.json` ([networking investigation](./networking-debugging.md#L53-L80)).
- The production wand app lacks the stream probe's IPv6-to-IPv4 relay, which may be required on an iPhone hotspot ([networking investigation](./networking-debugging.md#L90-L105)).
- Current self-signed cert is untrusted and SAN-bound to `192.168.18.6`. A new hotspot IP cannot use it without regeneration/trust.
- Phone section is intentionally plain HTTP/WS and does not need camera secure context. The standalone CV should run at `localhost` on the laptop; a LAN-IP camera page requires trusted HTTPS.

### Executable hotspot retest

1. Close `web/cvwand`, wand simulators, and stale servers. Enable the named phone hotspot and record provider/device privately.
2. Join laptop, UNO Q, and two phones to that hotspot over Wi-Fi (not laptop USB tether).
3. Run `ipconfig getifaddr en0`; if empty or not on the board's subnet, inspect other active interfaces. Record redacted laptop/board/phone addresses and topology.
4. Verify `ssh -4/-6 arduino@ArduinoUnoQ.local` (or numeric board IP). If IPv6-only, use the stream probe relay path.
5. Regenerate/deploy `wand_config.json` with the current laptop address; do not rely on container gateway discovery.
6. Regenerate a certificate containing the new laptop IP, install/trust its CA on laptop/phones, or keep camera on laptop `localhost` and sections on plain HTTP. Verify firewall inbound TCP 8080/8443 and hotspot client-to-client reachability.
7. Run:

   ```sh
   .venv/bin/python server/main.py
   ./firmware/uno_q/stream_probe/run_probe.sh \
     --board arduino@ArduinoUnoQ.local \
     --server-ip <current-hotspot-laptop-ip> \
     --keep-running
   python3 -m http.server 8765 --bind 127.0.0.1 --directory cv_hand_movements
   ```

8. Join two phones at `http://<laptop-ip>:8080/section/?s=lol1`, unlock audio, and record roster RTT/theta plus reconnects for at least five minutes.
9. Execute selection, shake-all, pause/resume, DET, and AI twice each; record gesture, wire event, server state, board feedback, visible phone/console result, audible scope, and latency.
10. Cycle board Wi-Fi/server and confirm cached identity, current song/transport, aim, and mode. The current mode-reset failure should be expected until fixed.

## 5. Deterministic mode versus AI mode

### Deterministic mode

The standalone two-finger pose emits `wand.mode {mode:"det"}` as an `admin` client. The server accepts the message, changes `session.wand.mode`, resets gesture windows and neutralizes prior effects, broadcasts roster, and sends board feedback ([mode dispatch](../../server/main.py#L480-L539)). The hardware owner remains the `role:wand` socket.

Every hardware IMU batch still enters `_update_aim`. In DET mode it calls `_expression` directly:

- `ay/9.8` is clamped to tilt `[-1,1]`;
- `pitch` maps to major-scale degrees/octaves;
- `volume` maps gain 0.3–1.2;
- `filter` maps to tension;
- output targets `aim` or `SECTION_ALL` ([expression](../../server/main.py#L738-L773)).

It does not call `RemoteModel.request`. Grabs are ignored in DET ([dispatch](../../server/main.py#L515-L518)). The isolated runtime observed full lift -> `+12` semitones on only `s2`, then full lift -> `section:all` during shake latch.

### AI mode

The standalone three-finger pose emits `wand.mode {mode:"ai"}`. Hardware then has two gesture paths:

- continuous raw IMU can commit a `StrokeTracker` stroke when not grabbing;
- ToF squeeze emits `wand.grab start/end`, and the IMU window between edges becomes `GestureFeatures` ([firmware squeeze](../../firmware/uno_q/wand/python/wand_link.py#L224-L253), [server router](../../server/wandio.py#L28-L83)).

`Conductor._gesture_in` writes into the currently aimed section's independent state, calls `RemoteModel.request(context)`, and lets scheduling continue ([gesture path](../../server/engine/conductor.py#L273-L313)). At a bar line, `_decide` consumes a fresh model answer if present/valid; otherwise it uses the heuristic ([decision](../../server/engine/conductor.py#L403-L431)). When shaping is active, `_take_generated` consumes an exact-index bar-model cache entry and prefetches two bars ahead; theory pads/ornaments cover if none lands ([bar model](../../server/engine/conductor.py#L455-L481), [render fallback](../../server/engine/conductor.py#L617-L750)).

Live current-process result:

```text
wand mode -> ai
gesture(s2) -> {...}
policy WARNING model ask failed (URLError) — heuristic covers
engine bar -> sustained [heuristic]
barmodel WARNING bar ask failed (URLError) — rule-based candidates only
```

The optional hardware-protocol `wand.gesture sharp_up` was used to trigger this path; that is runtime protocol evidence, not proof of physical IMU recognition. Direct Python diagnosis returned:

```text
URLError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
```

System `curl` returned HTTP 200 from both configured endpoints, so credentials/endpoints were present and reachable. No app response was parsed, cached, selected, scheduled, or heard. `"generated"` in roster only proves `RemoteBarModel.configured`, not a successful bar.

### Models/provider and documentation drift

Current sanitized configuration:

| Purpose | Current selection | Provider actually used |
|---|---|---|
| Decision | `WM_MODEL_NAME=flash-1784391958-0aa455cc`; URL host `clado-ai--freesolo-lora-serving.modal.run`; key set; timeout 2000 ms | Freesolo Modal endpoint, currently unusable by app due TLS verification (and measured curl latency exceeded timeout). |
| Bar line | `WM_BARMODEL_NAME=flash-1784407398-edf55491`; same Freesolo host; key set; timeout 7000 ms; prefetch 2 | Freesolo v3, currently unusable by app due TLS verification. |

`docs/MODELS.md` identifies Caellum's model/deployment as the merged bar-line v3 (`Caecae2k/wand-barline-v3`) on Caellum's Fireworks organization, selected by `WM_BARMODEL_URL` and `WM_BARMODEL_NAME=model#deployment`, normally with `WM_BARMODEL_PREFETCH=1` ([registry](../MODELS.md#L50-L68)). That is **not** the current process. The decision model is the Freesolo decision adapter in the registry ([registry](../MODELS.md#L8-L29)).

Stale/contradictory docs:

- `current-run-setup.md` claims a physical hardware wand in AI mode and working model wiring; the current live roster had CV/det/no phones, while current-checkout app requests failed TLS ([old claim](./current-run-setup.md#L20-L48)).
- `MODELS.md` says the live demo serves v3 with widened styles and separately describes Fireworks as the fast live host; current env is v3 on Freesolo with prefetch 2.
- `hardware-wand.md` says aiming solos/carries accompaniment on one phone; current requirement and conductor deliberately keep all instruments playing ([stale text](../hardware-wand.md#L47-L53)).
- `firmware/uno_q/TEST_PLAN.md` still directs full-loop CV through `web/cvwand/` and documents contention; the newer testing walkthrough correctly defines standalone admin + hardware wand ([stale plan](../../firmware/uno_q/TEST_PLAN.md#L100-L111), [golden rule](../../firmware/testing-walkthrough.md#L7-L21)).
- The testing walkthrough and standalone README still explicitly advertise pinch rewind/forward, contradicting the investigation requirement that it be disabled ([walkthrough](../../firmware/testing-walkthrough.md#L83-L92), [README](../../cv_hand_movements/README.md#L39-L46)).

## 6. Complete intended route traces

### 1. Left one finger -> Select -> physical aim -> UI

1. `cv_hand_movements`: MediaPipe `GestureRecognizer` -> `pickLeftHand` -> `classifyGesture` -> stabilized `ONE_FINGER` (`currentMode=SELECT`).
2. `ServerEmitter.mode(SELECT)` -> **no wire message**. `cv.state {gesture:"ONE_FINGER",mode:"SELECT"}` is telemetry only; server stores it in the admin connection's `extra`, not selection state.
3. UNO Q Movement -> MCU `Bridge.notify("imu", CSV)` -> Linux batch -> `wand.imu` on `ws://IP:8080/ws`.
4. Server `ImuTelemetry.ingest` -> `WandAimer.on_frames` integrates `gz` -> `resolve(placements)` -> `aim_section`.
5. `Conductor.on_aim(section)` sets `_aim`; roster `engine.aimed`, `wand.state.aim_section`, and `wand.cmd.aim` reflect it.
6. Console `applyEngine` -> `aimedGroup` -> `.card.aimed` glow.

**Difference:** step 2 is missing as a control hop. Aim operates continuously without Select, and the visual step was not observed in a browser.

### 2. Physical shake -> select all

1. UNO Q continuous `wand.imu` -> server `ShakeDetector`.
2. Four high-g rising peaks/600 ms -> `_select_all_until=now+1500` and log `wand.shake`.
3. `aim=None` -> `Conductor.on_aim(None)` clears per-section overrides.
4. `wand.state.aim_section=null`, roster `engine.aimed=null`, `wand.cmd.aim=null` -> console clears highlighted group/board clears aim.
5. DET outputs during latch use `section:"all"`.

**Difference:** this path is implemented for hardware, but “all” is transient and not a preserved selection. Physical recognition/feedback remains blocked.

### 3. Left fist -> server pause -> clients -> Arduino feedback

1. Intended: standalone recognizer returns `FIST`; actual risk: pinch priority may return `PINCH` first.
2. If `FIST`: `admin.cmd {cmd:"stop"}` from role `admin`.
3. Server `_admin`: `session.playing=false`; `Conductor.on_transport("stop")`; roster false; scheduler emits `sched.cancel {allnotesoff:true}`.
4. Phones/console call `synth.panic`; transport/playhead freezes. This is transport pause, not section mute/gain change.
5. Server `_notify_wand` sends `wand.cmd {playing:false}`; UNO Linux updates state and Bridge CSV; MCU play LED blinks.
6. Palm reverses the path with `start`, preserving `_next_bar_idx`; board LED becomes solid.

**Runtime:** steps 2–4 and state payload passed; steps 1, physical audio, and step 5 hardware LED are blocked. Step 1 has a proven classifier failure case.

### 4. Left two fingers -> DET -> physical IMU -> selected effect

1. Standalone `TWO_FINGERS` -> local `DETERMINISTIC` -> `wand.mode {mode:"det"}`.
2. Server `session.wand.mode="det"`; roster and `wand.cmd.mode` update; physical owner remains `variant:hw`.
3. UNO Q `wand.imu`; server aim plus `_expression` reads `ay`.
4. `fx.expr` or sectioned `fx.tension` broadcasts to sections/stage.
5. Selected phone applies effect; every other phone resets expression/tension to neutral and continues receiving its notes.

**Runtime:** protocol path passed (`s2 +12`, and `all +12` during latch); physical input/audio blocked.

### 5. Left three fingers -> AI -> physical gesture -> model/fallback -> notes

1. Standalone `THREE_FINGERS` -> local `AI` -> `wand.mode {mode:"ai"}`.
2. UNO Q streams IMU continuously; StrokeTracker commits a stroke, or ToF grab bounds a gesture window.
3. Server maps stroke/window to `GestureFeatures`; `Conductor._gesture_in` writes aimed/all state and starts `RemoteModel.request`.
4. Remote decision result, if valid and timely, becomes source `model`; otherwise `_decide` uses source `heuristic`.
5. At active arrangement bars, `RemoteBarModel.take(idx)` may supply `generated`; server prefetches `idx+2`. Missing/late/invalid response falls through to deterministic theory.
6. Per-section state shapes only selected section; null aim uses shared/global state. Scheduler broadcasts absolute-time notes; phones filter by destination and play.

**Current live result:** step 3 was reached via hardware protocol; both remote calls failed TLS, so heuristic/theory continued. No model or generated response was consumed, and phone audibility was blocked. The stale-aim ordering can make the first new-wand stroke target the previous/global state.

## Root causes and recommended fixes

| Failure/partial | First failing boundary and root cause | Specific recommendation | Risk / verification after fix |
|---|---|---|---|
| Physical/hotspot acceptance unavailable | External dependency: no board, hands, two phones, hotspot/provider access | Run the executable retest above with a named operator and capture all device outputs twice. | High demo risk. Rerun stream probe, two-phone audio/sync, LED, reconnect, all gestures, five-minute stability. |
| Select is local-only/continuous aim | Client protocol/state: no server `select` mode or selection latch; one finger only changes CV UI | Add explicit server selection state (e.g. `wand.select {active,target}` or validated `admin.cmd select`) driven by CV admin. Separate `pointed_section` from durable `selected_scope`; freeze selected target when leaving Select. | Medium-high. Add CV emitter tests, protocol authorization, two-section selection persistence, UI roster, and “aim outside Select does not retarget.” |
| Select-all expires | Server state: `_select_all_until` is only a 1.5 s debounce latch | Make shake write durable `selected_scope=all`; keep the 1.5 s value only as shake debounce. Clear/change it only in Select or explicit action. | Medium. Test beyond several seconds/bars and across DET/AI; ensure global fold semantics are intentional. |
| Pinch enabled | Correct CV client still routes local scrub and server rewind/forward | Remove/feature-disable standalone pinch transport code and update docs/tests to assert no timeline or wire action. | Low-medium. Unit test no `seek`, no `rewind/forward`, position unchanged in playing/paused states. |
| Fist swallowed by pinch | Gesture recognition priority checks pinch before `Closed_Fist` | Port the embedded route's fist-first rule: determine curled-four-finger fist before pinch, or honor high-confidence built-in `Closed_Fist` first. | Medium safety. Add landmark test exactly reproducing close-thumb fist plus physical lighting/angle trials. |
| Remote models never consumed | Model network boundary: Python `urllib` CA trust fails. Decision latency also exceeded 2 s in two curl samples | Use a maintained HTTP client/SSL context with a packaged CA bundle; log sanitized exception reason and elapsed time. Point the bar model to the documented Fireworks deployment if active, and set decision timeout to measured warm/cold SLO or use a fast deployment. | High for AI claim. Integration test real TLS endpoint in deployment environment; capture request ID, parse, `decision_source:model`, generated cache take, scheduled notes, and fallback reasons. |
| First stroke uses stale aim | Server ordering/state: stroke dispatch precedes applying current batch's aim; disconnect leaves `_last_aim`/engine aim | On owner connect/disconnect clear/revalidate aim and notify engine; in `_update_aim`, apply aim before dispatching stroke/DET effect. | High targeting risk. Regression with disconnected old section, first reconnect batch, simultaneous new aim+stroke; assert exact section. |
| Reconnect resets DET to AI | Server state: new default `WandSlot` replaces mode on every connect/disconnect | Persist authoritative mode/det param outside ephemeral connectivity, or carry prior values into the new slot; snapshot those on reconnect. | Medium. Same-client and new-socket reconnect tests while stopped/playing and during DET. |
| Flagship fallback missing | Asset/config boundary: `songs/zelda-fairy.mid` is absent; missing path silently leaves built-in | Either commit/provision the intended MIDI and validate it at startup, or document built-in loop as the default. Emit an explicit warning when configured default is absent. | Low implementation, medium demo-content risk. Clean boot with/without cache/default and corrupt cache. |
| Hotspot HTTPS fails | Network/certificate boundary: self-signed untrusted cert with old-IP SAN | Prefer laptop-local `localhost` for camera; generate/trust a local CA and per-network cert, or use a stable trusted hostname/tunnel appropriate for offline demo. Display current HTTP/HTTPS URLs and trust prerequisites. | High setup risk. Test fresh phone trust, new hotspot IP, WSS, camera permission, restart. |
| Docs/tests contradict behavior | Repository verification boundary: obsolete solo test, missing dataset, conflicting CV routes/model claims | Update documentation after behavior is chosen; rewrite `rework_test` for non-muting targeting; restore/generate bar dataset fixture; make one canonical hardware walkthrough. | Medium. Documentation walkthrough dry run by a second person; all automated suites green. |

No fix was implemented in this investigation.

## Prioritized next steps

### Required before the next hardware test

1. Fix standalone pinch disablement and fist-first recognition; add the missing regression tests.
2. Clear/reorder stale aim and preserve wand mode across reconnect.
3. Decide and implement durable Select/select-all semantics; one finger must have an actual server hop.
4. Fix Python TLS trust and confirm both remote clients with actual runtime consumption; choose current Freesolo versus Caellum Fireworks deliberately and align timeouts/prefetch.
5. Put the intended default MIDI in `songs/` or explicitly approve/document `loop-CGAmF`.
6. Prepare hotspot topology, current `wand_config.json`, cert/trust approach, board hostname/IP, two charged phones, and console audio-unlock steps.

### Required before the demo

1. Complete the full physical retest twice on the exact hotspot and retain sanitized logs.
2. Verify two-phone audible targeting: individual, all, and no muting of unselected instruments.
3. Verify physical fist/palm position continuity and board LED agreement.
4. Verify a real physical AI gesture produces a consumed `source:model` decision and, when needed, a consumed/scheduled generated bar; also rehearse traceable deterministic fallback.
5. Run five-minute reconnect/latency/sync soak and board power-cycle; eliminate reconnect loops and mode reset.
6. Update `current-run-setup.md`, model registry live-state language, hardware-wand aim semantics, TEST_PLAN, and stale automated tests.

### Optional improvements

1. Expose `pointed_section`, durable `selected_scope`, model request status/latency/failure reason, and generated-line source in admin telemetry.
2. Warn prominently when console audio is locked or the configured default song is missing.
3. Add a production IPv6 relay/discovery strategy matching the proven stream-probe implementation.
4. Add a scripted, non-physical two-section acceptance suite for aim/order/reconnect/selection scope while retaining separate physical gates.

## Compact retest checklist

- [ ] Record date/SHA/branch, machine, hotspot provider/device, redacted topology/IPs, and exact hardware/phones.
- [ ] Confirm laptop, UNO Q, and two phones share the same hotspot Wi-Fi; verify SSH and ports 8080/8443.
- [ ] Confirm cert trust/SAN and camera secure context; run standalone CV as `admin`, UNO Q as sole `wand`.
- [ ] Run `stream_probe_test.py`, CV tests, stroke tests, policy/bar tests, show test, and physical `run_probe.sh`; record totals.
- [ ] Confirm roster simultaneously shows CV admin, `wand {variant:hw}`, and two ready sections.
- [ ] Unlock both phone synths and console locally; start playback.
- [ ] One finger -> Select; point at phone A then B; capture gesture, wire, `wand.state`, roster, glow, and audible result.
- [ ] Shake physical wand; verify durable all selection beyond 1.5 s and across mode change.
- [ ] DET: tilt physical wand; verify only selected phone changes, then all changes, while every instrument keeps playing.
- [ ] Fist/palm twice: verify no pinch/seek, bar position continuity, global transport, phone/console audio, and board LED agreement; right hand must do nothing.
- [ ] AI: capture real physical gesture, decision request/reply/source, bar request/reply/cache take, scheduled destinations, and audible result/fallback reason.
- [ ] Disconnect/reconnect/power-cycle wand while playing; verify song, transport position, selection, mode, identity, and LEDs remain correct.
- [ ] Observe RTT/theta, audio sync, and reconnects for at least five minutes; record every failure at its first boundary.
