"""Song material. For the vertical slice this is a hardcoded 4-bar loop
(I–V–vi–IV in C major) with a simple melody, structured as `BarData` so a real
MIDI loader (pretty_midi) can replace `builtin_song()` later behind the same shape.

Rhythm grid: 16 sixteenth-note slots per bar (4/4). A note is (onset16, dur16, midi).
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.theory import triad

Note = tuple[int, int, int]  # (onset_16th, dur_16ths, midi)


@dataclass
class BarData:
    chord_root: int          # pitch class 0-11
    chord_minor: bool
    chord_pcs: tuple[int, int, int]
    melody: list[Note]


@dataclass
class Song:
    name: str
    bpm: float
    key_root: int            # pitch class of the key (0 = C)
    bars: list[BarData]

    def bar(self, i: int) -> BarData:
        return self.bars[i % len(self.bars)]


def _bar(root_pc: int, minor: bool, melody: list[Note]) -> BarData:
    return BarData(root_pc, minor, triad(root_pc, minor), melody)


def builtin_song() -> Song:
    # Quarter-note melody (onsets 0,4,8,12; each 4 sixteenths long), C-major.
    return Song(
        name="loop-CGAmF",
        bpm=100.0,
        key_root=0,  # C
        bars=[
            # I  — C major
            _bar(0, False, [(0, 4, 72), (4, 4, 76), (8, 4, 79), (12, 4, 76)]),
            # V  — G major
            _bar(7, False, [(0, 4, 74), (4, 4, 79), (8, 4, 83), (12, 4, 79)]),
            # vi — A minor
            _bar(9, True, [(0, 4, 72), (4, 4, 76), (8, 4, 81), (12, 4, 76)]),
            # IV — F major
            _bar(5, False, [(0, 4, 72), (4, 4, 77), (8, 4, 81), (12, 4, 77)]),
        ],
    )
