"""The candidate accompaniments. Each bar, every generator turns the melody +
chord into one musically-valid response; the ranker later picks one. All outputs
are snapped to the key and folded into a low accompaniment register so they sit
under the melody and can't clash.

A candidate note is (onset_16th, dur_16ths, midi, vel).
"""
from __future__ import annotations

from engine.song import BarData
from engine.theory import diatonic_transpose, snap_to_scale, voice_triad

CandNote = tuple[int, int, int, float]

REG_LO, REG_HI = 52, 71   # accompaniment register (E3..B4)


def _fit(midi: int) -> int:
    while midi > REG_HI:
        midi -= 12
    while midi < REG_LO:
        midi += 12
    return midi


def _clean(midi: int, key: int) -> int:
    return _fit(snap_to_scale(midi, key))


def lower_imitation(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    # Melody a diatonic third below, dropped an octave into the pad register.
    return [(on, dur, _clean(diatonic_transpose(m, key, -2) - 12, key), 0.75)
            for (on, dur, m) in bar.melody]


def contrary_motion(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    if not bar.melody:
        return []
    axis = bar.melody[0][2]
    return [(on, dur, _clean(2 * axis - m, key), 0.7)
            for (on, dur, m) in bar.melody]


def sustained(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    # Whole-bar triad, low close voicing.
    return [(0, 16, _clean(n, key), 0.55) for n in voice_triad(bar.chord_pcs)]


def delayed(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    # Echo the previous bar's melody an octave down (causal, always in key).
    return [(on, dur, _clean(m - 12, key), 0.65) for (on, dur, m) in prev.melody]


def rhythmic_dense(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    # Subdivide each melody note into repeated eighths, alternating with the
    # lower scale neighbour — a busier, higher-energy line.
    out: list[CandNote] = []
    for (on, dur, m) in bar.melody:
        base = _clean(m - 12, key)
        neighbour = _clean(diatonic_transpose(m, key, -1) - 12, key)
        half = max(2, dur // 2)
        out.append((on, half, base, 0.7))
        if dur >= 4:
            out.append((on + half, dur - half, neighbour, 0.65))
    return out


def rest(bar: BarData, prev: BarData, key: int) -> list[CandNote]:
    return []


GENERATORS = {
    "lower_imitation": lower_imitation,
    "contrary_motion": contrary_motion,
    "sustained": sustained,
    "delayed": delayed,
    "rhythmic_dense": rhythmic_dense,
    "rest": rest,
}

# Articulation hint sent to the synth per candidate type.
ART = {
    "sustained": "sustain",
    "rest": "sustain",
    "lower_imitation": "pluck",
    "contrary_motion": "pluck",
    "delayed": "pluck",
    "rhythmic_dense": "pluck",
}


def generate(bar: BarData, prev: BarData, key: int) -> dict[str, list[CandNote]]:
    return {name: gen(bar, prev, key) for name, gen in GENERATORS.items()}
