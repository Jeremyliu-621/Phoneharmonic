"""Score a deployed bar-line adapter, per style, against the exact GRPO judge.

For each eval row the deployed model answers the training prompt and the reward
from freesolo/barline/environment.py (imported with the SDK stubbed, same as
the dataset build) scores it — so "good" here means the SAME thing it meant at
data-build time and will mean at GRPO time. Reports per-style mean/min reward
and format-failure counts; the teacher labels score >=0.95 by the build gate,
so that's the bar a swap-in must approach.

Run:  python server/tools/eval_barmodel.py --model <run-id> [--per-style 12]
Env:  WM_BARMODEL_URL / WM_BARMODEL_KEY (serving endpoint + key)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

from build_bar_dataset import _load_reward

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
EVAL = REPO / "freesolo" / "barline" / "dataset" / "eval.jsonl"
STYLE_RE = re.compile(r'"style":"(\w+)"')


def ask(url: str, key: str, model: str, prompt: str, timeout: float = 60.0) -> str:
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "max_tokens": 200, "temperature": 0.2,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="deployed run id (serving model name)")
    ap.add_argument("--per-style", type=int, default=12)
    ap.add_argument("--styles", default="harmonize,passing,arpeggio,dense,calm")
    args = ap.parse_args()

    url = os.environ.get("WM_BARMODEL_URL", "")
    key = os.environ.get("WM_BARMODEL_KEY", "")
    if not url or not key:
        print("set WM_BARMODEL_URL and WM_BARMODEL_KEY")
        return 2

    reward = _load_reward()
    wanted = args.styles.split(",")
    rows: dict[str, list] = {s: [] for s in wanted}
    with open(EVAL, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            m = STYLE_RE.search(row["input"])
            s = m.group(1) if m else "?"
            if s in rows and len(rows[s]) < args.per_style:
                rows[s].append(row)

    overall_ok = True
    for style, batch in rows.items():
        if not batch:
            print(f"{style:10s}  (no eval rows)")
            continue
        scores, fails, teacher = [], 0, []
        for row in batch:
            teacher.append(reward(row["input"], row["output"]))
            r = 0.0
            for attempt in (1, 2, 3):   # retry serving hiccups; only a real
                try:                    # answer (or 3 strikes) scores the model
                    out = ask(url, key, args.model, row["input"])
                    r = reward(row["input"], out)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  [{style}] attempt {attempt} failed: {e}")
            if r < 0.25:            # below format floor = didn't even speak JSON
                fails += 1
            scores.append(r)
        mean = sum(scores) / len(scores)
        tmean = sum(teacher) / len(teacher)
        verdict = "OK" if (mean >= tmean - 0.05 and fails == 0) else "SHORT"
        overall_ok = overall_ok and verdict == "OK"
        print(f"{style:10s}  model {mean:.3f} (min {min(scores):.3f}, "
              f"{fails} format-fails)  teacher {tmean:.3f}  -> {verdict}")

    print("VERDICT:", "match — safe to allowlist" if overall_ok
          else "falls short — keep the deterministic layer / keeper")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
