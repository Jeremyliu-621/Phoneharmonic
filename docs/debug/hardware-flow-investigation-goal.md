# Goal: Verify the complete Phoneharmonic hardware performance flow

Investigate and verify the current Phoneharmonic demo flow end to end, using the
real Arduino UNO Q wand and real phones wherever hardware is available. Do not
write application code during this goal. The deliverable is a Markdown report of
findings, evidence, root causes, and recommended next steps.

Use [`docs/debug/current-run-setup.md`](./current-run-setup.md) as the starting
context, but do not assume its previous findings are still true. Re-verify them
against the current checkout and current live run.

## Constraints

- This is an investigation and verification goal, not an implementation goal.
- Do not modify server, web, CV, firmware, configuration, or test code.
- Do not modify `.env`, expose credentials, or include secrets in the report.
- Read-only commands, existing automated tests, server launches, browser
  inspection, WebSocket observation, logs, and hardware interaction are allowed.
- Prefer the real demo route and real hardware over simulators.
- Simulator or unit-test results may support a conclusion, but must never be
  reported as proof that the physical Arduino flow works.
- Clearly label anything that could not be tested because hardware, phones,
  hotspot access, credentials, or another dependency was unavailable.
- Do not silently substitute `web/cvwand/` for the Arduino. First identify and
  document the intended live route. In particular, determine whether the correct
  combined flow is the standalone `cv_hand_movements` client acting as `admin`
  while the UNO Q owns the wand slot, rather than the webcam client acting as a
  wand and competing with the physical device.
- Do not stop after static code inspection. For every item, collect the strongest
  available runtime evidence and distinguish `PASS`, `FAIL`, `PARTIAL`, and
  `BLOCKED`.

## Run setup

Start from the repository root and use the project virtual environment:

```sh
.venv/bin/python server/main.py
```

Use the URLs, ports, HTTPS notes, `.env` loading behavior, and console-audio
unlock caveat documented in `docs/debug/current-run-setup.md`. Confirm the actual
LAN IP printed by the current run instead of assuming the old
`192.168.18.6` address is still correct.

Before live testing, inspect the current documentation and relevant code paths,
including at minimum:

- `docs/debug/current-run-setup.md`
- `docs/demo_flow.md`
- `docs/hardware-wand.md`
- `firmware/testing-walkthrough.md`
- `firmware/uno_q/TEST_PLAN.md`
- `cv_hand_movements/`
- `web/cvwand/`
- `server/main.py`
- `server/engine/conductor.py`
- `server/ml/policy.py`
- `server/ml/barmodel.py`
- `server/config.py`

Run relevant existing automated tests before hardware tests. Record the exact
commands, pass/fail totals, and meaningful failures in the report. Do not repair
failing tests during this goal.

## Questions to answer

### 1. Selection and edit targeting

Verify the intended interaction:

1. The user's physical left hand enters Select mode with one finger.
2. Pointing the physical Arduino wand selects one individual phone/instrument.
3. The selected phone is visibly indicated in the UI and observable in live
   server/roster/wand telemetry.
4. Shaking the physical wand while in Select mode changes the target to all
   phones/instruments.
5. Entering Deterministic mode or AI mode afterward preserves the selection.
6. The subsequent edit affects only the selected phone, or affects all phones
   after select-all.
7. Selection changes edit targeting only; it must not mute or stop unselected
   instruments.

Test with at least two real phones if possible. For each transition, capture the
input gesture, the wire/server event, the reported selected section, the visible
UI result, and the audible result.

Pay special attention to whether shake-to-select-all exists only in the webcam
route and not in the Arduino route. If the hardware route does not implement it,
identify the exact missing hop: gesture recognition, firmware message, protocol
message, server handling, state update, or UI reflection. Report a concrete
implementation recommendation, but do not implement it.

### 2. Left-hand transport and disabled pinch behavior

Using the actual left-hand CV route used in the hardware demo, verify that:

- A closed left fist pauses playback rather than muting audio.
- An open left palm resumes playback.
- Pause preserves the current musical position and resume continues from that
  position rather than restarting at bar zero.
- The physical right hand does not trigger these controls.
- Pinch-based rewind/fast-forward is currently disabled and produces no timeline
  jump or unintended command.
- Pinch does not prevent a fist from being recognized as pause.
- The console, phones, server transport state, and Arduino feedback/LED remain in
  agreement after pause and resume.

Differentiate a real transport pause from browser autoplay muting, local audio
context suspension, per-section mute, gain zero, or an all-notes-off symptom.
Account for the console tab's local audio-unlock behavior described in the run
setup.

### 3. No-hardware fallback track

Verify behavior on a clean server start with the Arduino disconnected:

- Determine exactly which song is loaded: cached last song, configured default
  MIDI, or built-in hardcoded deterministic loop.
- Determine whether the claimed fallback to a completely deterministic or
  hardcoded track is accurate under current default conditions.
- Verify that playback remains usable without the wand.
- Then connect and disconnect the Arduino during a run and observe whether the
  song, transport, routing, or decision behavior changes unexpectedly.

Document the precedence among cached song, `WM_DEFAULT_SONG`, built-in song, and
any other fallback. If current behavior differs from the stated requirement,
identify the root cause and recommend the smallest implementation or
documentation change.

### 4. Hotspot operation

Repeat the real hardware flow on the intended phone hotspot network if access is
available. Do not treat ordinary LAN success as hotspot success.

Verify at minimum:

- The laptop's current hotspot IP is discovered or configured correctly.
- The UNO Q connects and remains connected without a reconnect loop.
- At least two phones can join as sections.
- HTTP/WS and HTTPS/WSS routes used by each device are correct.
- Certificate trust, secure-context camera restrictions, firewall rules, client
  isolation, and port reachability do not break the flow.
- Selection, select-all, pause/resume, deterministic edits, and AI edits still
  work on the hotspot.
- Audio synchronization and connection stability are acceptable for a demo.

Record the hotspot provider/device, topology, IPs with sensitive portions
redacted if needed, URLs used, observed latency/reconnect symptoms, and every
blocked step. If hotspot testing cannot be performed, mark it `BLOCKED`, explain
exactly what is missing, and provide a short executable retest procedure.

### 5. Deterministic mode versus AI mode

Explain the current runtime distinction using both code tracing and live
evidence.

For Deterministic mode, verify:

- The left-hand mode gesture actually changes the server's wand mode to `det`.
- The physical Arduino remains the active wand and continues streaming IMU.
- Wand movement/tilt maps directly to the configured deterministic parameter.
- No decision-model request is made because of the deterministic gesture.
- The resulting `fx.expr` or `fx.tension` targets the selected phone or all
  phones as expected.

For AI mode, verify:

- The left-hand mode gesture changes the server's wand mode to `ai`.
- A real physical-wand gesture reaches the conductor's AI gesture path.
- The decision model is called and its response can be distinguished from the
  heuristic fallback.
- The bar-line model is configured and actually called when its generated
  candidate is needed.
- The generated result is accepted, scheduled, and audible, or the system falls
  back deterministically with a traceable reason.
- Selection scopes the AI edit to the intended phone, while select-all scopes it
  globally.

Do not infer successful AI use merely because credentials exist, an endpoint
returns HTTP 200, `generated` appears in the candidates list, or the wand reports
AI mode. Capture evidence of an actual request and actual runtime consumption.
Likewise, do not call `decision_source: heuristic` a failure without determining
whether it is an expected timing fallback, parse failure, timeout, unavailable
response, or normal state before a model reply lands.

Identify which model/deployment belongs to Caellum, which environment variables
select it, and whether the current process is using Freesolo, Fireworks, another
endpoint, or no remote model. Never print keys. Compare the current environment
and behavior with `docs/MODELS.md` and report any stale or contradictory docs.

### 6. Complete intended route

Produce one verified end-to-end flow diagram or numbered trace showing the
actual live path for each of these:

1. Left-hand one-finger gesture → Select mode → physical wand aiming → selected
   section → UI indication.
2. Physical wand shake → select all.
3. Left-hand fist → server pause → phones/console pause → Arduino state feedback.
4. Left-hand two-finger gesture → deterministic mode → physical IMU → selected
   section effect.
5. Left-hand three-finger gesture → AI mode → physical gesture → decision model
   and/or heuristic → bar-line generation and/or deterministic fallback →
   selected section notes.

For every hop, name the responsible component, message/event, state field, and
runtime evidence. Highlight any point where the implemented route differs from
the intended demo flow.

## Root-cause procedure for failures

For every `FAIL` or `PARTIAL` result:

1. Reproduce it at least twice when practical.
2. Reduce it to the first failing boundary: recognition, client routing, network,
   protocol, wand-slot ownership, firmware bridge, server state, conductor,
   model request, scheduler, phone audio, or UI.
3. Cite the relevant files and line numbers.
4. State the root cause if proven; otherwise list the strongest hypothesis and
   what evidence would confirm it.
5. Recommend a specific fix or implementation approach.
6. Estimate risk and list the tests that should be added or rerun after the fix.

Do not implement the fix in this goal.

## Required deliverable

Create a new Markdown file at:

`docs/debug/hardware-flow-investigation-report.md`

The report must be self-contained and include:

1. Date, commit SHA, branch, machine/network context, and hardware actually used.
2. Executive summary with the overall readiness verdict.
3. A checklist table for every requirement with `PASS`, `FAIL`, `PARTIAL`, or
   `BLOCKED`.
4. Exact run route and launch commands.
5. Automated-test results.
6. Detailed evidence and observations for each investigation section above.
7. The verified deterministic-versus-AI explanation.
8. The complete end-to-end flow trace.
9. Root causes for every failure or unresolved behavior.
10. Recommended fixes or potential implementations, without making code changes.
11. Prioritized next steps divided into:
    - required before the next hardware test;
    - required before the demo;
    - optional improvements.
12. A compact retest checklist another person can follow.

Include concise log excerpts or sanitized payloads where useful. Link to relevant
repository files with line numbers. Never include credentials or full secret
values. Do not overwrite `docs/debug/current-run-setup.md`.

## Completion criteria

This goal is complete only when the report file exists and every requested
behavior has a status backed by evidence. Hardware-dependent items that could
not be exercised may remain `BLOCKED`, but the report must identify the exact
blocker and give precise next steps for completing those tests. A code-reading
summary alone is not completion.
