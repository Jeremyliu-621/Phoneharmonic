"""Minimal music theory: MIDI notes, the major scale, chords, and the two
operations the candidate generators need — snap-to-scale and diatonic transpose.

Pitches are MIDI integers internally (60 = middle C = "C4"). We convert to
scientific-pitch strings ("C4") only when emitting NoteEvents, because the
browser synth parses that format.
"""
from __future__ import annotations

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]   # semitone offsets of the major scale


def midi_to_name(m: int) -> str:
    return f"{NAMES[m % 12]}{m // 12 - 1}"


def scale_pcs(root: int) -> set[int]:
    """Pitch classes (0-11) of the major scale rooted at `root`."""
    return {(root + i) % 12 for i in MAJOR}


def scale_notes(root: int, lo: int = 36, hi: int = 96) -> list[int]:
    pcs = scale_pcs(root)
    return [n for n in range(lo, hi + 1) if n % 12 in pcs]


def snap_to_scale(midi: int, root: int) -> int:
    """Nearest note in the major scale of `root` (ties resolve downward)."""
    pcs = scale_pcs(root)
    if midi % 12 in pcs:
        return midi
    for d in range(1, 7):
        if (midi - d) % 12 in pcs:
            return midi - d
        if (midi + d) % 12 in pcs:
            return midi + d
    return midi


def diatonic_transpose(midi: int, root: int, steps: int) -> int:
    """Move `midi` by `steps` scale degrees (negative = down), staying in key."""
    notes = scale_notes(root)
    m = snap_to_scale(midi, root)
    if m not in notes:
        m = min(notes, key=lambda n: abs(n - m))
    i = notes.index(m)
    j = max(0, min(len(notes) - 1, i + steps))
    return notes[j]


def triad(root_pc: int, minor: bool) -> tuple[int, int, int]:
    """Pitch classes of a major/minor triad on `root_pc`."""
    third = 3 if minor else 4
    return (root_pc % 12, (root_pc + third) % 12, (root_pc + 7) % 12)


def voice_triad(pcs: tuple[int, ...], base: int = 48) -> list[int]:
    """Voice a set of pitch classes as MIDI notes in a low pad register [base, base+12)."""
    return sorted(base + ((pc - base) % 12) for pc in pcs)
