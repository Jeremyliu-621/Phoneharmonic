# Current run setup (2026-07-19)

How Chloe is currently running the stack, plus what's been verified live in
this session.

## Launch

```
.venv/bin/python server/main.py
```

Console: `https://192.168.18.6:8443/console/` (LAN IP `192.168.18.6`, HTTPS
because mkcert certs exist in `certs/` — see `config.py:964-972`). Plain
`:8080` also serves sections/ESP32 wand over http/ws.

`server/config.py` loads `<repo>/.env` on import (`config.py:17-23`), so no
extra env setup is needed beyond dropping keys in `.env` — real shell env
still wins if set.

## Model wiring — confirmed live, working

Verified by connecting to the running server as an `admin` WS client and
reading the live `roster.engine` payload, plus a direct curl against the
model endpoint using the `.env` credentials:

- `WM_MODEL_URL` / `WM_MODEL_NAME` / `WM_MODEL_KEY` (decision model) and
  `WM_BARMODEL_URL` / `WM_BARMODEL_NAME` / `WM_BARMODEL_KEY` (bar-line model)
  are both set in `<repo>/.env`, pointing at the same Freesolo Modal deploy
  (`clado-ai--freesolo-lora-serving.modal.run/v1`), different adapter run IDs.
- `roster.engine.candidates` included `"generated"` → `self._barmodel.configured
  == True` on the running process (`conductor.py:133`) → `.env` loaded
  correctly.
- Direct `curl` to `WM_MODEL_URL/chat/completions` with `WM_MODEL_NAME`/
  `WM_MODEL_KEY` returned `HTTP 200` in ~1.1s with a real completion —
  endpoint reachable, auth good, well inside `WM_MODEL_TIMEOUT_MS` (2000ms).
- `roster.wand` showed the physical UNO Q wand connected and in **AI mode**:
  `{'connected': True, 'variant': 'hw', 'mode': 'ai', 'det_param': 'pitch'}`.
  AI mode is what gates `Conductor._gesture_in()` calling
  `self._model.request(...)` (`conductor.py:260`) — det mode never touches
  the model, it drives `fx.expr`/`fx.tension` straight from tilt
  (`main.py:728-761`).
- `roster.engine.decision_source` read `"heuristic"` at the moment checked —
  expected/fine: heuristic silently covers whenever the model's async reply
  hasn't landed for the current bar (`ml/policy.py:6-8`); it's not a sign of
  breakage given the endpoint tested healthy.

Net: decision model + bar-line model are both correctly wired to the wand's
AI mode and functioning as designed. No code changes were needed.

## Gotcha: console tab audio requires its own local unlock

At the time of checking, `roster.sections == []` (no phones joined), so per
`conductor.py:446-459` the engine correctly routes accompaniment as
`SECTION_ALL` — the console/laptop is meant to be the fallback speaker when
no phones are connected.

But `web/console/console.js:462-469` only actually calls `synth.schedule(e)`
when a page-local `started` flag is `true`, and that flag is **only** set by
clicking the console's own ▶ **Start** button (`console.js:505-508`), which
also calls `synth.unlock()` (browser autoplay policy) and re-sends
`admin.cmd: start`. It is not synced from server state.

Symptom: if the show gets started some other way — e.g. the hardware wand
sending `admin.cmd: start` directly (`main.py:460-463`) — `session.playing`
flips `true` server-side, notes stream to the console and get drawn on the
piano-roll (`ingest()` always runs), but nothing plays, because that
browser tab's `started` never got set.

Fix: click ▶ Start in the console UI itself at least once per tab load.
Side effect: this re-anchors the transport (restarts the bar counter from 0)
even if the wand had already started the show, since it's the same
`admin.cmd: start` path.
