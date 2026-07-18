"""Generate the Wand Maestro pixel-art UI asset set via the Retro Diffusion API.

Cohesion strategy (this is what makes the set look designed, not random):
  * one MODEL + STYLE for all sprites,
  * one shared prompt SUFFIX,
  * one SEED base (per-asset offset kept stable),
  * remove_bg on every sprite so they composite onto the stage,
  * an optional shared PALETTE image (see `palette` command) locked across assets.

The API token is a SECRET. It's read from $RD_TOKEN or server/tools/rd_token.txt
(both gitignored) — never hardcode it and never commit it.

Usage (run from repo root or server/):
  python server/tools/gen_assets.py credits            # free: show remaining balance
  python server/tools/gen_assets.py cost [names...]    # free dry-run: price a batch
  python server/tools/gen_assets.py list               # show the asset manifest
  python server/tools/gen_assets.py gen NAME [NAME...]  # generate specific assets
  python server/tools/gen_assets.py all                # generate the whole set

Generated PNGs land in web/assets/ (tracked — clients serve them; the token never ships).
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

# Windows consoles default to cp1252; force UTF-8 so status glyphs don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

API = "https://api.retrodiffusion.ai/v1"
SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent
OUT_DIR = REPO_DIR / "web" / "assets"
TOKEN_FILE = SERVER_DIR / "tools" / "rd_token.txt"

# --- shared aesthetic knobs -------------------------------------------------
# "Wand Maestro": a magical 16-bit concert — cute chibi musicians on a dark
# stage, warm footlights + a glowing magic wand. One style + suffix + seed keep
# every sprite in the same world.
MODEL = "rd_plus__default"          # quality tier for the hero pass; swap to rd_fast__default for cheap bulk
SEED = 7777
SUFFIX = ("16-bit SNES JRPG pixel art, cute chibi proportions, clean crisp pixels, "
          "warm stage footlights with cool magical glow, dark navy background")

# name -> (prompt, width, height, remove_bg, style_override|None, tile)
ASSETS: dict[str, tuple] = {
    # --- Layered stage: composites in z-order back->front so nothing floats and
    # the curtains genuinely frame (and occlude) the musicians. Replaces bg_stage.
    "hall_back": ("empty theater stage interior seen from the audience: deep midnight-blue "
                  "back wall with a few faint golden stars, a warm spotlit wooden plank stage "
                  "floor receding backward, soft rim light. NO curtains, no drapes, no arch, "
                  "no columns, no audience seats — a bare simple stage",
                  448, 256, False, "rd_plus__environment", False),
    "curtain_side": ("one tall luxurious deep red velvet theater side curtain hanging down the "
                     "LEFT edge, gathered and draped with a gold rope tie and tassel, ornate gold "
                     "trim, a single isolated curtain panel and nothing else",
                     112, 256, True, None, False),
    "valance": ("a deep red velvet theater curtain valance swag with gold fringe and tassels "
                "draped across the very top, ornate pelmet, empty space below it, a single "
                "isolated object at the top and nothing else", 448, 128, True, None, False),
    "seats": ("two rows of empty theater audience seats, dark red velvet chairs seen from "
              "behind along the bottom, empty space above them, a single isolated row of "
              "seats and nothing else", 448, 128, True, None, False),

    # Backdrop (no transparency; tileable left-right so we can pan/repeat it).
    "bg_stage": ("empty grand concert hall stage seen from the audience, red velvet "
                 "curtains, wooden floor, spotlights, magical particles in the air, "
                 "wide scenic environment", 448, 256, False, "rd_plus__environment", False),

    # One chibi musician per instrument family (transparent — composited on the stage).
    "violin":  ("a cute chibi musician playing a violin", 128, 160, True, None, False),
    "cello":   ("a cute chibi musician playing a cello", 128, 160, True, None, False),
    "flute":   ("a cute chibi musician playing a flute", 128, 160, True, None, False),
    "trumpet": ("a cute chibi musician playing a trumpet", 128, 160, True, None, False),
    "drums":   ("a cute chibi musician playing a drum kit", 128, 160, True, None, False),
    "piano":   ("a cute chibi musician playing a grand piano keyboard", 128, 160, True, None, False),
    "harp":    ("a cute chibi musician playing a harp", 128, 160, True, None, False),
    "synth":   ("a cute chibi musician playing a glowing neon synthesizer keyboard", 128, 160, True, None, False),

    # Conductor-side props.
    "wand":    ("a magical conductor's wand with a glowing star tip, sparkles, "
                "single item, plain background", 128, 128, True, None, False),
    "podium":  ("a wooden conductor's podium with a music stand, single object", 128, 128, True, None, False),

    # VFX + UI.
    "note_pulse": ("a single glowing golden musical note bursting with light, sparkles",
                   64, 64, True, None, False),
    "ui_panel":   ("a fantasy game UI panel frame, ornate border, empty middle, dark",
                   256, 128, False, "rd_plus__ui_element", False),
}


def token() -> str:
    tok = os.environ.get("RD_TOKEN")
    if tok:
        return tok.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    sys.exit(f"No token. Set $RD_TOKEN or write it to {TOKEN_FILE}")


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers={"X-RD-Token": token(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:400]}") from None


def _get(path: str) -> dict:
    req = urllib.request.Request(API + path, headers={"X-RD-Token": token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _payload(name: str, check_cost: bool = False) -> dict:
    prompt, w, h, rembg, style, tile = ASSETS[name]
    p = {
        "prompt": f"{prompt}, {SUFFIX}",
        "prompt_style": style or MODEL,
        "width": w,
        "height": h,
        "num_images": 1,
        "seed": SEED,
        "remove_bg": rembg,
    }
    if tile:
        p["tile_x"] = True
    if check_cost:
        p["check_cost"] = True
    return p


def cmd_credits() -> None:
    try:
        info = _get("/inferences/credits")
        print(json.dumps(info, indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"credits check failed: {type(e).__name__}: {e}")
        raise


def cmd_cost(names: list[str]) -> None:
    names = names or list(ASSETS)
    total = 0.0
    for n in names:
        try:
            r = _post("/inferences", _payload(n, check_cost=True))
            c = r.get("cost", r.get("balance_cost", 0.0))
            total += c
            print(f"  {n:12s} ${c:.4f}  ({ASSETS[n][1]}x{ASSETS[n][2]}, {ASSETS[n][4] or MODEL})")
        except Exception as e:  # noqa: BLE001
            print(f"  {n:12s} cost check failed: {e}")
    print(f"  {'TOTAL':12s} ${total:.4f}  ({len(names)} assets)")


def cmd_gen(names: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    for n in names:
        if n not in ASSETS:
            print(f"  ! unknown asset {n!r} (see `list`)")
            continue
        try:
            r = _post("/inferences", _payload(n))
            imgs = r.get("base64_images") or []
            if not imgs:
                print(f"  ! {n}: no image in response: {r}")
                continue
            out = OUT_DIR / f"{n}.png"
            out.write_bytes(base64.b64decode(imgs[0]))
            spent += r.get("balance_cost", 0.0)
            print(f"  ✓ {n:12s} -> {out.relative_to(REPO_DIR)}  "
                  f"(${r.get('balance_cost', 0):.4f}, bal ${r.get('remaining_balance', 0):.2f})")
        except Exception as e:  # noqa: BLE001
            print(f"  ! {n}: {type(e).__name__}: {e}")
    print(f"  spent ${spent:.4f} this run")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    rest = args[1:]
    if cmd == "credits":
        cmd_credits()
    elif cmd == "cost":
        cmd_cost(rest)
    elif cmd == "gen":
        if not rest:
            sys.exit("gen needs at least one asset name (see `list`)")
        cmd_gen(rest)
    elif cmd == "all":
        cmd_gen(list(ASSETS))
    elif cmd == "list":
        for n, (p, w, h, rb, st, tl) in ASSETS.items():
            print(f"  {n:12s} {w}x{h}  {'transparent' if rb else 'opaque'}  {st or MODEL}")
    else:
        sys.exit(f"unknown command {cmd!r}. Try: credits | cost | list | gen NAME | all")


if __name__ == "__main__":
    main()
