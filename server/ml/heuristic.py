"""Heuristic ranker v0: hand-written mapping from gesture features to a preferred
accompaniment candidate. This is the swappable `Ranker` — the learned model (P5)
implements the same rank()/choose() and drops in behind the same interface.

Intuition:
  big/fast gesture   -> busy, energetic line   (rhythmic_dense)
  gentle / still     -> hold a chord or rest    (sustained / rest)
  twist / swirl      -> interweaving counter-line (contrary_motion)
  sharp short flick  -> echo the last bar        (delayed)
  raise / lower      -> shift the chosen line up/down an octave
"""
from __future__ import annotations

from gestures.features import GestureFeatures


def rank(gf: GestureFeatures | None, candidate_types: list[str]) -> dict[str, float]:
    e = gf.energy if gf else 0.0
    size = gf.size if gf else 0.0
    vert = gf.vertical if gf else 0.0
    rot = gf.rotation if gf else 0.0
    dur = gf.duration if gf else 0.0
    energy_intent = 0.6 * e + 0.4 * size

    scores: dict[str, float] = {}
    for t in candidate_types:
        if t == "rest":
            s = 0.65 * (1 - energy_intent) - 0.25
        elif t == "sustained":
            # calm, or a clear lift, or the no-gesture default
            s = 0.45 * (1 - energy_intent) + 0.45 * max(0.0, vert) + (0.35 if gf is None else 0.0)
        elif t == "lower_imitation":
            s = 0.45 + 0.25 * (1 - abs(energy_intent - 0.5) * 2)
        elif t == "contrary_motion":
            s = 0.30 + 1.20 * rot + 0.25 * max(0.0, -vert)
        elif t == "delayed":
            flick = 1.0 if (dur and dur < 0.6) else 0.35
            s = 0.20 + 0.80 * energy_intent * flick
        elif t == "rhythmic_dense":
            s = 0.10 + 1.30 * energy_intent
        elif t == "generated":
            # A freshly model-written line (only offered when one has arrived):
            # attractive for flowing mid-energy gestures, outbid by dense/counter
            # at the extremes where the rule-based lines are the right answer.
            s = 0.55 + 0.35 * energy_intent
        else:
            s = 0.0
        scores[t] = s
    return scores


def choose(scores: dict[str, float], last_choice: str | None) -> str:
    # Small penalty for repeating the same candidate, so held gestures still evolve.
    adjusted = dict(scores)
    if last_choice in adjusted:
        adjusted[last_choice] -= 0.15
    return max(adjusted, key=adjusted.get)


def octave_shift(gf: GestureFeatures | None) -> int:
    """A strong raise/lower nudges the chosen line up/down an octave."""
    if gf is None:
        return 0
    if gf.vertical > 0.6:
        return 12
    if gf.vertical < -0.6:
        return -12
    return 0
