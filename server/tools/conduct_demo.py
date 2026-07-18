"""Render ONE audio file walking a song through conductor instructions — v2,
with real orchestration instead of knob-turning.

The vocabulary (all material derived from the song itself):
  - HUSH (approved v1): beat-grid simplification, softer, tempo eases.
  - SWELL: texture layers fade in — accompaniment doubled an octave up, bass
    reinforced an octave down, a soft string pad on the song's own chords.
  - BUILD: the layers arrive one per bar, dynamics and tempo ramping, ending
    in a breath (luftpause)...
  - CLIMAX: ...then a ROLLED ensemble chord, melody doubled an octave up,
    at forte (not fortissimo — loud is not noise).
  - RELEASE: a softer re-entry, then the file exactly as written.

Run:  python server/tools/conduct_demo.py [songs/zelda-fairy.mid]
Out:  songs/conducted-demo.wav + printed section map
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

os.environ.setdefault("WM_DECISION_LOG", "0")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

from engine.midi_load import load_midi_bytes
from engine.theory import midi_to_name
from engine_api import NoteEvent
from render_preview import REPO, render

# (label, thin, vel, tempo, pad, bass8vb, acc8va, double_mel, roll_chord, luft)
SCORE = (
    [("neutral", 0, 1.00, 1.00, 0, 0, 0, 0, 0, 0)] * 8
    + [("hush",    1, 0.60, 0.94, 0, 0, 0, 0, 0, 0)] * 2
    + [("hush",    2, 0.50, 0.92, 0, 0, 0, 0, 0, 0)] * 2
    + [("swell",   0, 1.10, 1.02, 1, 1, 1, 0, 0, 0)] * 4
    + [("build",   0, 0.95, 0.98, 1, 0, 0, 0, 0, 0)]
    + [("build",   0, 1.05, 1.00, 1, 1, 0, 0, 0, 0)]
    + [("build",   0, 1.15, 1.03, 1, 1, 1, 0, 0, 1)]
    + [("CLIMAX",  0, 1.25, 1.04, 1, 1, 1, 1, 1, 0)]
    + [("release", 0, 0.85, 0.97, 0, 0, 0, 0, 0, 0)]
    + [("release", 0, 1.00, 1.00, 0, 0, 0, 0, 0, 0)] * 3
)


def thin(notes: list, level: int) -> list:
    if level <= 0 or not notes:
        return notes
    step = 2 if level == 1 else 4
    kept = [n for n in sorted(notes) if (n[0] % step) < 0.26]
    return kept or sorted(notes)[:1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("midi", nargs="?", default=str(REPO / "songs" / "zelda-fairy.mid"))
    args = ap.parse_args()
    song, _parts = load_midi_bytes(pathlib.Path(args.midi).read_bytes(),
                                   pathlib.Path(args.midi).name)
    base_bar_ms = 60_000.0 / song.bpm * 4

    events: list[NoteEvent] = []
    t = 0.0
    nid = 0

    def emit(at, dur, midi, vel, inst):
        nonlocal nid
        nid += 1
        events.append(NoteEvent(f"c{nid}", "all", at, dur, midi_to_name(max(24, min(96, midi))),
                                round(min(1.0, vel), 3), "pluck", inst))

    print("section map:")
    for bar_i, (label, level, vmul, tmul, pad, bass8, acc8, dbl, roll, luft) in enumerate(SCORE):
        bar_ms = base_bar_ms / tmul
        s16 = bar_ms / 16
        if bar_i == 0 or SCORE[bar_i - 1][0] != label:
            print(f"  {t/1000:5.1f}s  {label}")
        bar = song.bar(bar_i % len(song.bars))
        for part in song.parts:
            if part.is_drum:
                continue
            raw = part.bars[bar_i % len(part.bars)]
            notes = raw if part.is_melody else thin(raw, level)
            for (on, dur, midi, vel) in notes:
                if luft and on >= 14:            # the breath before the climax
                    continue
                v = vel * (max(0.85, vmul) if part.is_melody else vmul)
                emit(t + on * s16, dur * s16, midi, v, part.instrument)
                if part.is_melody and dbl:       # climax: melody shines an octave up
                    emit(t + on * s16, dur * s16, midi + 12, v * 0.7, "violin")
                if not part.is_melody:
                    lowest = midi < 55
                    if bass8 and lowest:         # bass reinforced an octave down
                        emit(t + on * s16, dur * s16, midi - 12, v * 0.6, "cello")
                    if acc8 and not lowest:      # accompaniment shimmer an octave up
                        emit(t + on * s16, dur * s16, midi + 12, v * 0.45, part.instrument)
        if pad:                                  # soft string pad on the song's own chord
            for j, pc in enumerate(sorted(bar.chord_pcs)):
                emit(t, bar_ms * 0.96, 55 + ((pc - 7) % 12) + (12 if j == 2 else 0),
                     0.22, "viola")
        if roll:                                 # rolled ensemble chord, low to high
            root = sorted(bar.chord_pcs)[0]
            for j, (off, inst, v) in enumerate([(-24, "cello", 0.8), (-12, "viola", 0.7),
                                                (0, "harp", 0.65), (12, "harp", 0.55)]):
                emit(t + j * 35.0, bar_ms * 0.9, 60 + root + off, v, inst)
        t += bar_ms

    out = REPO / "songs" / "conducted-demo.wav"
    render(events, t, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
