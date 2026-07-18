# Training the AI (two models on Freesolo)

The orchestra has **two trained brains**, both served as OpenAI-compatible
endpoints, both with instant rule-based fallbacks — the music can never stall
on a network call:

1. **Decision model** ("input → action"): given the musical context and the
   conductor's gesture, pick the accompaniment and register —
   `{"candidate": "rhythmic_dense", "octave_shift": 0}`. Replaces the
   hand-written ranker (`server/ml/heuristic.py`).
2. **Bar-line model** ("music editing"): given key/chord/melody and a style
   directive, *write a new accompaniment line note-by-note* —
   `{"notes": [[onset, dur, midi, vel], ...]}`. It appears in the engine as
   the extra candidate **"generated"**, prefetched one bar ahead, and every
   reply is sanitized (snapped to key, folded into register, clamped to the
   grid) so the model supplies contour and rhythm while the engine guarantees
   playability.

Both contracts live in `server/ml/schema.py` — the single source of truth for
the server parser, the dataset builders, and the GRPO `structured_outputs`.

**Verified facts** (checked 2026-07-18): Freesolo is at **freesolo.co** (not
.ai). Runs are pre-quoted fixed-price (`--cost`); small LoRA runs finish in
minutes-to-hours for single-digit dollars; `flash deploy` gives an
OpenAI-compatible endpoint. Critical rule: **`structured_outputs` is only
valid for GRPO/OPD — an SFT config containing it is rejected at submit.**

## The pipeline

```
                 DECISION MODEL                      BAR-LINE MODEL
play sessions -> server/data/decisions/*.jsonl   folder of .mid files (optional)
                        |                                 |
        tools/build_dataset.py                tools/build_bar_dataset.py
        (harvest + synthetic + TASTE_RULES)   (theory pairs + real arrangements)
                        |                                 |
        freesolo/decision/dataset/            freesolo/barline/dataset/
                        |                                 |
        flash train decision/configs/{sft,rl}  flash train barline/configs/{sft,rl}
                        |                                 |
        flash deploy -> WM_MODEL_URL/NAME/KEY  flash deploy -> WM_BARMODEL_URL/NAME/KEY
                        \_________________________________/
                                python server/main.py
                    (heuristic + rule-generators cover all failures)
```

## Division of labor

**On this machine (no account needed) — all built and tested:**
- Harvest data: run the server, conduct; every bar logs a training row, wand
  thumbs up/down weight them (`WM_DECISION_LOG=0` disables).
- Build datasets: `python server/tools/build_dataset.py` and
  `python server/tools/build_bar_dataset.py [--midi-dir songs/]`.
- Encode taste: edit `TASTE_RULES` in build_dataset.py (label overrides where
  your judgment disagrees with the heuristic) and feed the bar model MIDIs in
  the style the orchestra should speak.
- Rehearse without any deploy: `python server/tools/mock_model.py`, then start
  the server with the printed env vars — the full AI-enabled system runs
  against local stand-ins. This is also the on-stage fallback if the venue
  loses internet.
- Verify: `python server/tools/policy_test.py` and `barmodel_test.py`.

**On Freesolo (account + credits), per model:**
```bash
uv tool install freesolo-flash
flash login --api-key                 # dashboard key
flash env setup                       # scaffold; reconcile freesolo/<model>/ with it
flash env push                        # uploads environment + dataset/

flash train freesolo/decision/configs/sft.toml --cost   # fixed quote first, always
flash train freesolo/decision/configs/sft.toml
flash train freesolo/decision/configs/rl.toml --cost
flash train freesolo/decision/configs/rl.toml           # GRPO vs environment.py
flash deploy <run-id>
```
Then export the env vars and restart the server:
```bash
export WM_MODEL_URL=https://<host>/v1    WM_MODEL_NAME=<decision-run> WM_MODEL_KEY=<key>
export WM_BARMODEL_URL=https://<host>/v1 WM_BARMODEL_NAME=<barline-run> WM_BARMODEL_KEY=<key>
python server/main.py
```
Sanity-check any deploy with the plain OpenAI SDK/curl before wiring it in.

## Recommended training order (hackathon clock)

1. **Decision SFT** first — smallest model (0.8b/2b), minutes to train, and
   the demo story ("the model that picks the music was trained today on my
   conducting") lands immediately. Ship it, keep playing.
2. **Bar-line SFT** next (4b if the quote allows) — the flashier capability:
   the orchestra plays lines no rule wrote. `--midi-dir` data makes or breaks
   the phrasing; even 20-50 MIDIs help.
3. **GRPO both** once SFT adapters exist and you've heard their failure
   modes — the rewards (`freesolo/*/environment.py`) are already written:
   decision = format + gesture-consistency + shift-intent + don't-repeat;
   bar-line = format + grid + in-key + register + style match + melody
   clearance. Chain each from its SFT run.
4. **Re-harvest and retrain** — every rehearsal logs more rows; a second SFT
   pass the night before the demo is cheap and real.

Reward/heuristic sync warning: the GRPO environments inline ports of
`heuristic.rank` and `barmodel.sanitize_line` — if you tune those, re-port.

## What the server does at run time

- **Decision**: asked async on every completed gesture, ~800ms budget
  (`WM_MODEL_TIMEOUT_MS`); its answer holds until the next gesture; editor
  override > model > heuristic; a new gesture clears any stale answer. The
  roster's `engine.decision_source` shows which brain made the last call.
- **Bar-line**: prefetched for bar N+1 while bar N plays (~2.4s of headroom,
  `WM_BARMODEL_TIMEOUT_MS`); arrives as candidate "generated", which the
  ranker favors for flowing mid-energy gestures, the decision model can pick
  by name, and the editor can force ("AI-written line"). A missed bar just
  means the six rule-based candidates compete alone.
- Every decision, from either brain or the fallback, is logged back into the
  harvest — playing the instrument improves the next training run.

## Other AI integrations (scoped, not yet built)

- **Voice drops** (ElevenLabs `eleven_flash_v2_5` WebSocket, ~100-150ms
  end-to-end): a server hook that announces set moments; free tier is ~10
  min/month — the $6 Starter tier covers a demo weekend.
- **Set-memory commentator** (Backboard.io — MLH partner, $5 free credits):
  one assistant with cross-thread memory fed section joins/drops and gesture
  stats; its ElevenLabs-voiced lines become the "DJ drop" layer. Backboard is
  a stateful assistant API, not a router — fan-out stays in our server.
- **Solana cNFT** of the finished set (Crossmint staging/devnet, one REST
  call): hash of the decision log + stats in the metadata. Helius's mint API
  is deprecated; don't use it.
