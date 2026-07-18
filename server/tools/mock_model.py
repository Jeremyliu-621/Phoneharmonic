"""A local stand-in for BOTH Freesolo deploys: an OpenAI-compatible
/v1/chat/completions that answers decision prompts with the heuristic ranker
and bar-line prompts with the rule-based generators (velocity-jittered).
Lets the complete AI-enabled system run — and the demo be rehearsed with the
hardware wand — before any real model is deployed, and stays the on-stage
fallback if the venue loses internet:

  WM_MODEL_URL=http://127.0.0.1:8901/v1    WM_MODEL_NAME=mock \\
  WM_BARMODEL_URL=http://127.0.0.1:8901/v1 WM_BARMODEL_NAME=mock \\
  python server/main.py

Run:  python server/tools/mock_model.py [--port 8901]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

from build_bar_dataset import STYLE_GEN
from engine.song import BarData
from engine.theory import triad
from gestures.features import GestureFeatures
from ml.policy import heuristic_decision

_rng = random.Random(11)


def _context_of(prompt: str) -> dict | None:
    i = prompt.rfind("Context: ")
    if i < 0:
        return None
    try:
        obj = json.loads(prompt[i + 9:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def answer(prompt: str) -> str:
    ctx = _context_of(prompt) or {}
    if "melody" in ctx:                          # bar-line request
        key = int(ctx.get("key", 0))
        ch = ctx.get("chord") or {}
        root, minor = int(ch.get("root", key)), bool(ch.get("minor", False))
        bar = BarData(root, minor, triad(root, minor),
                      [tuple(n) for n in ctx.get("melody", [])])
        prev = BarData(root, minor, triad(root, minor),
                       [tuple(n) for n in ctx.get("prev_melody", [])])
        gen = STYLE_GEN.get(ctx.get("style"), STYLE_GEN["free"])
        notes = gen(bar, prev, key) or STYLE_GEN["calm"](bar, prev, key)
        jittered = [[o, d, m, round(max(0.1, min(1.0, v + _rng.uniform(-0.1, 0.1))), 2)]
                    for (o, d, m, v) in notes]
        return json.dumps({"notes": jittered})
    g = ctx.get("gesture")                       # decision request
    d = heuristic_decision(GestureFeatures(**g) if g else None, ctx.get("prev"))
    return json.dumps({"candidate": d.candidate, "octave_shift": d.octave_shift})


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            content = answer(body["messages"][-1]["content"])
        except Exception:  # noqa: BLE001 - a bad request just gets an empty reply
            content = "{}"
        out = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def serve_in_thread(port: int = 0) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8901)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    base = f"http://127.0.0.1:{args.port}/v1"
    print(f"mock model serving {base}  (decision + bar-line)")
    print(f"  WM_MODEL_URL={base} WM_MODEL_NAME=mock "
          f"WM_BARMODEL_URL={base} WM_BARMODEL_NAME=mock python server/main.py")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
