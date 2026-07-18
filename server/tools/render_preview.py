"""Render a song offline through the SAME pipeline the browser plays (samples,
envelopes, panning, conducting envelope) and write wav files you can audition
without the server. This is the shared audible artifact: when something sounds
wrong live, render it here and we're both pointing at the same waveform.

Writes two files per song:
  songs/preview-neutral.wav    — 8 bars untouched (must sound like the file)
  songs/preview-conducted.wav  — big wave at bar 2, gentle at bar 8 (the breathing)

Run:  python server/tools/render_preview.py songs/zelda-fairy.mid
"""
from __future__ import annotations

import argparse
import math
import os
import pathlib
import struct
import subprocess
import sys
import wave

os.environ.setdefault("WM_DECISION_LOG", "0")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

from engine.conductor import Conductor
from engine.midi_load import load_midi_bytes
from engine.theory import NAMES

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SF = REPO / "web" / "assets" / "sf"
SR = 44100

SAMPLE_MAP = {"piano": "acoustic_grand_piano", "violin": "violin", "viola": "viola",
              "cello": "cello", "flute": "flute", "clarinet": "clarinet",
              "trumpet": "trumpet", "bass": "acoustic_bass", "harp": "orchestral_harp",
              "bell": "music_box"}
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
PAN = {"piano": 0, "violin": 0.35, "viola": 0.2, "cello": -0.3, "flute": 0.45,
       "clarinet": -0.4, "trumpet": 0.3, "bass": -0.15, "harp": -0.35, "bell": 0.45}

_cache: dict[str, list[float]] = {}


def name_to_midi(note: str) -> int:
    pc = NAMES.index(note[:-1]) if note[:-1] in NAMES else 0
    return (int(note[-1]) + 1) * 12 + pc


def load_sample(inst: str, midi: int):
    folder = SAMPLE_MAP.get(inst)
    if not folder:
        return None, 0
    sm = max(36, min(96, 36 + round((midi - 36) / 3) * 3))
    path = SF / folder / f"{FLATS[sm % 12]}{sm // 12 - 1}.mp3"
    key = str(path)
    if key not in _cache:
        if not path.exists():
            _cache[key] = []
        else:
            raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "f32le",
                                  "-ac", "1", "-ar", str(SR), "-"],
                                 capture_output=True).stdout
            _cache[key] = list(struct.unpack(f"<{len(raw) // 4}f", raw))
    return _cache[key], (midi - sm)


def render(events, total_ms: float, out_path: pathlib.Path) -> None:
    n = int(total_ms / 1000 * SR) + SR
    left, right = [0.0] * n, [0.0] * n
    for e in events:
        if e.art == "drum":
            continue                               # percussion synthesized; skip in preview
        data, semis = load_sample(e.inst or "piano", name_to_midi(e.note))
        if not data:
            continue
        rate = 2 ** (semis / 12)
        # The envelope must reach zero BEFORE the sample runs out, or every
        # note ends in a truncation click (hundreds of them = "static").
        avail = len(data) / SR / rate - 0.02
        dur = min(e.dur / 1000, max(0.08, avail - 0.1))
        tail = max(0.05, min(0.4, avail - dur))
        length = int((dur + tail) * SR)
        start = int(e.at / 1000 * SR)
        p = PAN.get(e.inst or "", 0.0)
        lg = math.cos((p + 1) * math.pi / 4) * e.vel * 0.3
        rg = math.sin((p + 1) * math.pi / 4) * e.vel * 0.3
        atk = int(0.012 * SR)
        rel_start = int(dur * SR)
        for k in range(length):
            src_i = k * rate
            i0 = int(src_i)
            if i0 + 1 >= len(data):
                break
            frac = src_i - i0
            s = data[i0] * (1 - frac) + data[i0 + 1] * frac
            if k < atk:
                env = k / atk
            elif k > rel_start:
                env = max(0.0, 1.0 - (k - rel_start) / (tail * SR))
            else:
                env = 1.0
            j = start + k
            if 0 <= j < n:
                left[j] += s * env * lg
                right[j] += s * env * rg
    peak = max(1e-6, max(max(map(abs, left)), max(map(abs, right))))
    norm = min(1.0, 0.85 / peak)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for l, r in zip(left, right):
            frames += struct.pack("<hh", int(l * norm * 32767), int(r * norm * 32767))
        w.writeframes(bytes(frames))
    print(f"wrote {out_path}  ({total_ms/1000:.1f}s, peak norm {norm:.2f})")


def pull_bars(c: Conductor, k: int, events: list) -> None:
    for _ in range(k):
        s = c._next_bar_start
        events.extend(c.get_events(s, s))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("midi", help="path to a .mid under songs/")
    args = ap.parse_args()
    data = pathlib.Path(args.midi).read_bytes()
    song, parts = load_midi_bytes(data, pathlib.Path(args.midi).name)

    from gesture_test import imu_window  # noqa: E402  (tools dir import)

    c = Conductor()
    c.load_song(song, parts)
    c.on_transport("start", 0.0)
    ev: list = []
    pull_bars(c, 8, ev)
    render(ev, c._next_bar_start, REPO / "songs" / "preview-neutral.wav")

    c2 = Conductor()
    c2.load_song(song, parts)
    c2.on_transport("start", 0.0)
    ev2: list = []
    pull_bars(c2, 2, ev2)
    c2.on_gesture(imu_window(accel_mag=12.0, dur_s=0.5))
    pull_bars(c2, 6, ev2)
    c2.on_gesture(imu_window(accel_mag=0.3, dur_s=0.25, n=10))
    pull_bars(c2, 6, ev2)
    render(ev2, c2._next_bar_start, REPO / "songs" / "preview-conducted.wav")
    return 0


if __name__ == "__main__":
    sys.exit(main())
