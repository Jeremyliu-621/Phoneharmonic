"""Freesolo GRPO environment for the bar-line (music editing) model.

score_response() is the reward. It runs on Freesolo's workers, so everything
is inlined — sync by hand with server/ml/barmodel.sanitize_line and
engine/candidates.py (register window) if those change.

Reward shape (0..1):
  0.25  format: exactly {"notes": [...]}, rows are 4-number lists
  0.20  grid: onset 0-15, dur >= 1, onset+dur <= 16, <= 16 notes
  0.20  in key (major scale of the context key)
  0.10  register (E3..B4 accompaniment window, MIDI 52-71)
  0.15  style match (dense/calm/counter/echo/free heuristics)
  0.10  melody clearance (no semitone/tritone clash on overlapping notes)

Reconcile with the scaffold `flash env setup` generates: keep its
load_environment() return shape and wire score_response in as the reward;
the dataset sidecar is freesolo/barline/dataset/ (build_bar_dataset.py).
"""
from __future__ import annotations

import json

MAJOR = [0, 2, 4, 5, 7, 9, 11]
REG_LO, REG_HI = 52, 71
CLASH = {1, 6, 11}   # semitone / tritone against the melody


def _pcs(root: int) -> set[int]:
    return {(root + i) % 12 for i in MAJOR}


def _context_from(prompt: str) -> dict | None:
    marker = "Context: "
    i = prompt.rfind(marker)
    if i < 0:
        return None
    try:
        obj = json.loads(prompt[i + len(marker):].strip())
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _rows_of(obj) -> list | None:
    if not isinstance(obj, dict) or set(obj) != {"notes"} or not isinstance(obj["notes"], list):
        return None
    rows = []
    for r in obj["notes"]:
        if (isinstance(r, list) and len(r) == 4
                and all(isinstance(v, (int, float)) for v in r)):
            rows.append(r)
    return rows


def _grid_ok(r: list) -> bool:
    on, dur = r[0], r[1]
    return 0 <= on <= 15 and dur >= 1 and on + dur <= 16


def _style_score(rows: list, context: dict) -> float:
    style = context.get("style", "free")
    n = len(rows)
    mean_dur = sum(r[1] for r in rows) / n
    if style == "dense":
        return 1.0 if (n >= 5 and mean_dur <= 3) else 0.3
    if style == "calm":
        return 1.0 if (n <= 4 and mean_dur >= 6) else 0.3
    if style == "counter":
        melody = context.get("melody") or []
        if len(melody) < 2 or n < 2:
            return 0.5
        mel_dir = melody[-1][2] - melody[0][2]
        line_dir = rows[-1][2] - rows[0][2]
        return 1.0 if mel_dir * line_dir < 0 else 0.3
    if style == "echo":
        prev = context.get("prev_melody") or []
        if not prev:
            return 0.5
        prev_pcs = {int(p[2]) % 12 for p in prev}
        hit = sum(1 for r in rows if int(r[2]) % 12 in prev_pcs)
        return 1.0 if hit >= n / 2 else 0.3
    return 1.0  # free: anything playable is fine


def _clearance(rows: list, context: dict) -> float:
    melody = context.get("melody") or []
    if not melody:
        return 1.0
    clashes = 0
    for r in rows:
        for m in melody:
            overlap = r[0] < m[0] + m[1] and m[0] < r[0] + r[1]
            if overlap and int(abs(r[2] - m[2])) % 12 in CLASH:
                clashes += 1
                break
    return 1.0 - clashes / len(rows)


def score_response(prompt: str, response: str) -> float:
    try:
        obj = json.loads(response)
    except (TypeError, ValueError):
        return 0.0
    rows = _rows_of(obj)
    if not rows:
        return 0.0
    context = _context_from(prompt) or {}
    key_pcs = _pcs(int(context.get("key", 0)))

    reward = 0.25 * (len(rows) / max(1, len(obj["notes"])))
    reward += 0.20 * (sum(1 for r in rows if _grid_ok(r)) / len(rows))
    reward += 0.20 * (sum(1 for r in rows if int(r[2]) % 12 in key_pcs) / len(rows))
    reward += 0.10 * (sum(1 for r in rows if REG_LO <= r[2] <= REG_HI) / len(rows))
    reward += 0.15 * _style_score(rows, context)
    reward += 0.10 * _clearance(rows, context)
    return min(1.0, reward)


def load_environment():
    """Keep the return shape of the load_environment() that `flash env setup`
    scaffolds for your account version; this dict form is a placeholder."""
    return {"reward": score_response, "dataset": "dataset"}
