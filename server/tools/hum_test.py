"""Headless test of hum-to-melody: a synthetic pitch contour (with tracker
noise) must come back as the right quantized song, and the conductor must
play it.

Run:  python server/tools/hum_test.py     (from repo root)
"""
from __future__ import annotations

import os
import pathlib
import random
import sys

os.environ["WM_DECISION_LOG"] = "0"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

from engine.conductor import Conductor
from engine.hum import song_from_pitches


def contour(notes, step_ms=18, noise=0.15, seed=3):
    """Continuous hum: (midi, start_ms, dur_ms) notes as noisy pitch frames."""
    rng = random.Random(seed)
    frames = []
    for (midi, start, dur) in notes:
        t = start
        while t < start + dur:
            frames.append([t, midi + rng.uniform(-noise, noise), 0.5 + rng.uniform(0, 0.2)])
            t += step_ms
    return frames


def main() -> int:
    print("[1] a hummed C-E-G-E comes back quantized, in key, in register")
    frames = contour([(60, 0, 600), (64, 600, 600), (67, 1200, 600), (64, 1800, 600)])
    song = song_from_pitches(frames, 100.0)
    assert song is not None, "no song heard"
    assert song.key_root == 0, f"expected C, got {song.key_root}"
    mel = song.bars[0].melody
    assert [(on, m) for (on, _d, m) in mel] == [(0, 72), (4, 76), (8, 79), (12, 76)], mel
    assert song.bars[0].chord_root == 0, song.bars[0].chord_root   # downbeat C -> C major
    assert not song.bars[0].chord_minor
    print(f"    melody {mel}, key=C, chord=C major")

    print("[2] octave register folding (a low hum lands in the melody register)")
    low = contour([(48, 0, 600), (52, 600, 600), (55, 1200, 600)])
    song2 = song_from_pitches(low, 100.0)
    assert song2 and all(65 <= m <= 84 for (_o, _d, m) in song2.bars[0].melody), song2.bars[0].melody
    print(f"    {song2.bars[0].melody}")

    print("[3] garbage in -> None out (never a crash, never a broken song)")
    assert song_from_pitches([], 100.0) is None
    assert song_from_pitches([[0, 60, 0.5]] * 4, 100.0) is None          # too short
    assert song_from_pitches([[0], ["x"], [1, 2], None], 100.0) is None  # malformed
    print("    ok")

    print("[4] the conductor plays the hummed song")
    c = Conductor()
    c.load_song(song, [])
    c.on_transport("start", 0.0)
    ev = c.get_events(0.0, 0.0)
    notes = {e.note for e in ev}
    assert ev and "C5" in notes, f"hummed melody not heard in {sorted(notes)}"
    assert c.status()["song"] == "hummed melody"
    print(f"    {len(ev)} events, melody root C5 present")

    print("\nALL HUM CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nHUM TEST FAILED: {e}")
        sys.exit(1)
